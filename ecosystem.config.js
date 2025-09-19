module.exports = {
  apps : [{
    name: 'whatsapp-service',
    script: 'manage.py',
    args: 'runserver 0.0.0.0:8001',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
  }]
};