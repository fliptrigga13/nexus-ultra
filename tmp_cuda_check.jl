using CUDA
println("CUDA Functional: ", CUDA.functional())
if CUDA.functional()
    println("Using GPU: ", CUDA.name(CUDA.device()))
    println("Memory Info: ", CUDA.memory_info())
else
    println("CUDA NOT DETECTED - FALLING BACK TO CPU")
end
