module.exports = {
  apps: [
    {
      name: 'send-message-scheduler',
      script: 'send_scheduled_message.py',
      interpreter: '/opt/whatsapp_service/enve/bin/python3',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      cron_restart: '30 2 * * *',  // Runs at 2:30 AM every day
      env: {
        NODE_ENV: 'development',
        DJANGO_SETTINGS_MODULE: 'UnderdogCrew.settings',
      },
      env_production: {
        NODE_ENV: 'production',
        DJANGO_SETTINGS_MODULE: 'UnderdogCrew.settings',
      }
    }
  ]
};