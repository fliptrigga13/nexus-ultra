# ============================================================
#  NEXUS ULTRA — PSO SWARM BRAIN
#  Particle Swarm Optimization | Julia + CUDA GPU Engine
#  Port: 7700  |  WebSocket: /ws  |  Control: POST /api/control
# ============================================================

using Pkg

# ── Auto-install required packages if missing ───────────────
# Use try/catch import so it works with or without a Project.toml
for pkg in ["CUDA", "HTTP", "JSON3"]
    try
        @eval using $(Symbol(pkg))
    catch
        println("  [PSO] Installing $pkg (first run — please wait)...")
        Pkg.add(pkg)
        @eval using $(Symbol(pkg))
    end
end

using CUDA
using HTTP
using HTTP.WebSockets
using JSON3
using Base.Threads: Atomic

# ────────────────────────────────────────────────────────────
#  GPU CHECK — fallback to CPU Arrays if CUDA unavailable
# ────────────────────────────────────────────────────────────
const USE_GPU = CUDA.functional()

if USE_GPU
    println("  [PSO] ✅ CUDA GPU detected: $(CUDA.name(CUDA.device()))")
else
    println("  [PSO] ⚠️  No CUDA GPU detected — running on CPU (Float32 Arrays)")
end

# Helper: create array on GPU or CPU transparently
make_array(x) = USE_GPU ? CuArray(x) : x
rand_array(T, dims...) = USE_GPU ? CUDA.rand(T, dims...) : rand(T, dims...)
zeros_array(T, dims...) = USE_GPU ? CUDA.zeros(T, dims...) : zeros(T, dims...)

# ────────────────────────────────────────────────────────────
#  PSO HYPER-PARAMETERS
# ────────────────────────────────────────────────────────────
const N_PARTICLES  = 128       # swarm size (power-of-2 for GPU warps)
const N_DIMS       = 10        # Rosenbrock dimensionality
const BOUNDS_LO    = -5.0f0
const BOUNDS_HI    =  5.0f0
const W            = 0.7f0     # inertia weight
const C1           = 1.4f0     # cognitive coefficient
const C2           = 1.4f0     # social coefficient
const MAX_ITER     = 1_000
const CONV_THRESH  = 1.0f-4   # convergence threshold
const PORT         = 7700

# ────────────────────────────────────────────────────────────
#  ROSENBROCK — CUDA KERNEL
#  Evaluates f(x) for each particle in parallel.
#  Each GPU thread handles one particle.
# ────────────────────────────────────────────────────────────
function rosenbrock_kernel!(fitness, x, n_particles, n_dims)
    idx = (blockIdx().x - 1) * blockDim().x + threadIdx().x
    if idx <= n_particles
        s = 0.0f0
        for i in 1:(n_dims - 1)
            xi  = x[idx, i]
            xi1 = x[idx, i + 1]
            s  += (1.0f0 - xi)^2 + 100.0f0 * (xi1 - xi^2)^2
        end
        fitness[idx] = s
    end
    return nothing
end

# ── CPU fallback for fitness evaluation ─────────────────────
function rosenbrock_cpu!(fitness, x, n_particles, n_dims)
    for idx in 1:n_particles
        s = 0.0f0
        for i in 1:(n_dims - 1)
            xi  = x[idx, i]
            xi1 = x[idx, i + 1]
            s  += (1.0f0 - xi)^2 + 100.0f0 * (xi1 - xi^2)^2
        end
        fitness[idx] = s
    end
end

# ── Unified dispatch ─────────────────────────────────────────
function eval_fitness!(fitness, x)
    if USE_GPU
        nthreads = 128
        nblocks  = cld(N_PARTICLES, nthreads)
        @cuda threads=nthreads blocks=nblocks rosenbrock_kernel!(
            fitness, x, N_PARTICLES, N_DIMS)
        CUDA.synchronize()
    else
        # CPU path: both arrays are plain Julia Arrays
        x_cpu  = x isa Array ? x : Array(x)
        fi_cpu = fitness isa Array ? fitness : Array(fitness)
        rosenbrock_cpu!(fi_cpu, x_cpu, N_PARTICLES, N_DIMS)
        if !(fitness isa Array)
            copyto!(fitness, fi_cpu)
        end
    end
end

# ────────────────────────────────────────────────────────────
#  SWARM STATE (module-level so HTTP handlers can read it)
# ────────────────────────────────────────────────────────────
mutable struct SwarmState
    x       :: Any   # positions      [N_PARTICLES × N_DIMS]
    v       :: Any   # velocities     [N_PARTICLES × N_DIMS]
    p_best  :: Any   # personal bests [N_PARTICLES × N_DIMS]
    p_fit   :: Any   # personal best fitness [N_PARTICLES]
    fitness :: Any   # current fitness [N_PARTICLES]
    g_best  :: Vector{Float32}   # global best position (CPU for logging)
    g_fit   :: Float32           # global best fitness
    iter    :: Int
    running :: Bool
    converged :: Bool
end

function make_swarm()
    x      = make_array(rand(Float32, N_PARTICLES, N_DIMS) .* (BOUNDS_HI - BOUNDS_LO) .+ BOUNDS_LO)
    v      = zeros_array(Float32, N_PARTICLES, N_DIMS)
    p_best = copy(x)
    fitness= zeros_array(Float32, N_PARTICLES)
    p_fit  = fill(Inf32, N_PARTICLES) |> make_array

    eval_fitness!(fitness, x)

    # Pull to CPU to find global best
    fit_cpu = Array(fitness)
    best_idx = argmin(fit_cpu)

    g_best = Array(x)[best_idx, :]
    g_fit  = fit_cpu[best_idx]

    # Sync p_best fitness
    copyto!(p_fit, fitness)

    SwarmState(x, v, p_best, p_fit, fitness, g_best, g_fit, 0, false, false)
end

# ────────────────────────────────────────────────────────────
#  PSO UPDATE — one iteration
# ────────────────────────────────────────────────────────────
function pso_step!(sw::SwarmState)
    r1 = rand_array(Float32, N_PARTICLES, N_DIMS)
    r2 = rand_array(Float32, N_PARTICLES, N_DIMS)

    # Broadcast g_best to GPU row matrix for vectorised ops
    g_best_gpu = make_array(repeat(sw.g_best', N_PARTICLES, 1))

    # Velocity update: v = w*v + c1*r1*(p_best - x) + c2*r2*(g_best - x)
    sw.v .= W .* sw.v .+
            C1 .* r1 .* (sw.p_best .- sw.x) .+
            C2 .* r2 .* (g_best_gpu .- sw.x)

    # Position update + clamping
    sw.x .= clamp.(sw.x .+ sw.v, BOUNDS_LO, BOUNDS_HI)

    # Evaluate new fitness
    eval_fitness!(sw.fitness, sw.x)

    # Update personal bests (where new fitness is better)
    fit_cpu    = Array(sw.fitness)
    p_fit_cpu  = Array(sw.p_fit)
    x_cpu      = Array(sw.x)
    p_best_cpu = Array(sw.p_best)

    improved_any_global = false
    for i in 1:N_PARTICLES
        if fit_cpu[i] < p_fit_cpu[i]
            p_fit_cpu[i]    = fit_cpu[i]
            p_best_cpu[i,:] = x_cpu[i,:]

            if fit_cpu[i] < sw.g_fit
                sw.g_fit  = fit_cpu[i]
                sw.g_best = x_cpu[i, :]
                improved_any_global = true
            end
        end
    end

    # Push updated personal bests back to GPU
    copyto!(sw.p_fit,  make_array(p_fit_cpu))
    copyto!(sw.p_best, make_array(p_best_cpu))

    sw.iter += 1
    sw.converged = sw.g_fit < CONV_THRESH
end

# ────────────────────────────────────────────────────────────
#  TRAINING LOOP (runs in background @async task)
# ────────────────────────────────────────────────────────────
const SWARM      = Ref{SwarmState}()
const STOP_FLAG  = Atomic{Bool}(false)
const CLIENTS    = Set{Any}()

function broadcast_frame()
    sw   = SWARM[]
    frame = Dict(
        "iter"      => sw.iter,
        "g_fit"     => sw.g_fit,
        "g_best"    => sw.g_best,
        "converged" => sw.converged,
        "running"   => sw.running,
        "gpu"       => USE_GPU,
        "device"    => USE_GPU ? string(CUDA.name(CUDA.device())) : "CPU"
    )
    local json_str
    try
        json_str = JSON3.write(frame)
    catch e
        println("  [PSO] Frame serialise error: $e")
        return
    end
    dead = Set{Any}()
    for ws in CLIENTS
        try
            HTTP.WebSockets.send(ws, json_str)
        catch
            push!(dead, ws)
        end
    end
    for ws in dead
        delete!(CLIENTS, ws)
    end
end

function run_pso_loop()
    SWARM[] = make_swarm()
    sw = SWARM[]
    sw.running  = true
    sw.converged = false
    STOP_FLAG[]  = false

    println("  [PSO] 🚀 Training started | $N_PARTICLES particles × $N_DIMS dims | max $MAX_ITER iters")

    for _ in 1:MAX_ITER
        if STOP_FLAG[]
            println("  [PSO] 🛑 Stopped by user at iter $(sw.iter)")
            break
        end
        pso_step!(sw)
        broadcast_frame()
        sleep(0.02)   # ~50 fps telemetry
        if sw.converged
            println("  [PSO] ✅ Converged at iter $(sw.iter) | fitness=$(sw.g_fit)")
            break
        end
    end

    sw.running = false
    broadcast_frame()
    println("  [PSO] Training ended | best fitness = $(sw.g_fit)")
end

# ────────────────────────────────────────────────────────────
#  HTTP / WEBSOCKET SERVER
# ────────────────────────────────────────────────────────────
function handle_ws(ws)
    push!(CLIENTS, ws)
    println("  [PSO] WS client connected (total: $(length(CLIENTS)))")
    # Send current state immediately on connect
    if isassigned(SWARM)
        broadcast_frame()
    else
        # Send a ready ping
        try
            HTTP.WebSockets.send(ws, JSON3.write(Dict("status" => "ready", "gpu" => USE_GPU,
                "device" => USE_GPU ? string(CUDA.name(CUDA.device())) : "CPU")))
        catch; end
    end
    try
        while true
            data = HTTP.WebSockets.receive(ws)
            data === nothing && break
        end
    catch e
        # EOFError / IOError = client disconnected
    finally
        delete!(CLIENTS, ws)
        println("  [PSO] WS client disconnected (total: $(length(CLIENTS)))")
    end
end

function router(req::HTTP.Request)
    path   = req.target
    method = req.method

    if path == "/health"
        return HTTP.Response(200, ["Content-Type" => "application/json"],
            JSON3.write(Dict("status" => "ok", "gpu" => USE_GPU)))

    elseif path == "/api/control" && method == "POST"
        body = JSON3.read(String(req.body))
        # JSON3 parses keys as Symbols — check both Symbol and String for safety
        action = string(get(body, :action, get(body, "action", "")))

        if action == "start"
            if isassigned(SWARM) && SWARM[].running
                return HTTP.Response(200, ["Content-Type" => "application/json"],
                    JSON3.write(Dict("status" => "already_running")))
            end
            @async run_pso_loop()
            return HTTP.Response(200, ["Content-Type" => "application/json"],
                JSON3.write(Dict("status" => "started")))

        elseif action == "stop"
            STOP_FLAG[] = true
            return HTTP.Response(200, ["Content-Type" => "application/json"],
                JSON3.write(Dict("status" => "stopping")))

        else
            return HTTP.Response(400, ["Content-Type" => "application/json"],
                JSON3.write(Dict("error" => "unknown action: $action")))
        end

    elseif path == "/api/state"
        if isassigned(SWARM)
            sw = SWARM[]
            return HTTP.Response(200, ["Content-Type" => "application/json"],
                JSON3.write(Dict("iter" => sw.iter, "g_fit" => sw.g_fit,
                    "running" => sw.running, "converged" => sw.converged,
                    "gpu" => USE_GPU)))
        else
            return HTTP.Response(200, JSON3.write(Dict("status" => "idle")))
        end

    else
        return HTTP.Response(404, "Not Found")
    end
end

# ────────────────────────────────────────────────────────────
#  MAIN ENTRY POINT
# ────────────────────────────────────────────────────────────
println("""
╔══════════════════════════════════════════════════╗
║   NEXUS ULTRA — PSO SWARM BRAIN  (Julia/CUDA)   ║
║   GPU: $(rpad(USE_GPU ? "✅ " * (USE_GPU ? string(CUDA.name(CUDA.device())) : "N/A") : "⚠️  CPU Fallback", 40))║
║   Listening on http://0.0.0.0:$PORT              ║
║   WebSocket : ws://0.0.0.0:$PORT/ws              ║
╚══════════════════════════════════════════════════╝
""")

# Initialise SWARM to idle state so /api/state works immediately
SWARM[] = make_swarm()
SWARM[].running = false

server = HTTP.listen!("0.0.0.0", PORT) do http::HTTP.Stream
    if HTTP.WebSockets.is_upgrade(http.message)
        HTTP.WebSockets.upgrade(http) do ws
            handle_ws(ws)
        end
    else
        req  = http.message
        resp = router(req)

        # CORS headers for the HTML dashboard
        push!(resp.headers, "Access-Control-Allow-Origin" => "*")
        push!(resp.headers, "Access-Control-Allow-Methods" => "GET, POST, OPTIONS")
        push!(resp.headers, "Access-Control-Allow-Headers" => "Content-Type")

        HTTP.setstatus(http, resp.status)
        for (k, v) in resp.headers
            HTTP.setheader(http, k => v)
        end
        HTTP.startwrite(http)
        write(http, resp.body)
    end
end

println("  [PSO] Server running. Open pso-trainer.html in your browser.")
println("  [PSO] Press CTRL+C to stop.")
wait(server)
