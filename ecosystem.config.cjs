// NEXUS ULTRA — PM2 Process Ecosystem
// Manages all services autonomously with auto-restart + crash recovery

module.exports = {
  apps: [
    {
      name: 'nexus-hub',
      script: 'server.cjs',
      cwd: 'c:\\Users\\fyou1\\Desktop\\New folder\\nexus-ultra',
      watch: false,
      autorestart: true,
      max_restarts: 20,
      min_uptime: '5s',
      restart_delay: 3000,
      max_memory_restart: '512M',
      env: { NODE_ENV: 'production', PORT: 3000 },
      log_file: 'logs/hub.log',
      error_file: 'logs/hub-err.log',
      time: true
    },
    {
      name: 'nexus-eh',
      script: 'nexus_eh.py',
      interpreter: 'python',
      cwd: 'c:\\Users\\fyou1\\Desktop\\New folder\\nexus-ultra',
      watch: false,
      autorestart: true,
      max_restarts: 20,
      min_uptime: '8s',
      restart_delay: 5000,
      max_memory_restart: '400M',
      log_file: 'logs/eh.log',
      error_file: 'logs/eh-err.log',
      time: true
    },
    {
      name: 'nexus-swarm',
      script: 'nexus_swarm_loop.py',
      interpreter: 'python',
      cwd: 'c:\\Users\\fyou1\\Desktop\\New folder\\nexus-ultra',
      watch: false,
      autorestart: true,
      max_restarts: 10,
      min_uptime: '15s',
      restart_delay: 10000,
      max_memory_restart: '600M',
      log_file: 'logs/swarm.log',
      error_file: 'logs/swarm-err.log',
      time: true
    }
  ]
};
