module.exports = {
  apps: [{
    name: 'whatsapp-service',
    script: 'newrelic-admin',
    args: 'run-program python manage.py runserver 0.0.0.0:8001',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
  }]
};