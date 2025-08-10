module.exports = {
  apps: [
    {
      name: 'low-credit-notification',
      script: 'send_low_credit_notification.py',
      interpreter: '/opt/whatsapp_service/enve/bin/python3',
      autorestart: false,
      watch: false,
      max_memory_restart: '1G',
      cron_restart: '30 2 * * *',  // Runs at 2:30 AM  UTC every day
      env: {
        NODE_ENV: 'development',
        DJANGO_SETTINGS_MODULE: 'UnderdogCrew.settings'
      },
      env_production: {
        NODE_ENV: 'production',
        DJANGO_SETTINGS_MODULE: 'UnderdogCrew.settings'
      }
    }
  ]
}; 