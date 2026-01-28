module.exports = {
  apps: [{
    name: 'whatsapp-service',
    script: '/opt/python_apis/enve/bin/python',
    args: 'manage.py runserver 0.0.0.0:8001',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G'
  }]
};