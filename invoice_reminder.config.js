module.exports = {
  apps: [
    {
      name: 'whatsapp-invoice-reminder',
      script: 'send_invoice_reminders.py',
      interpreter: '/opt/whatsapp_service/enve/bin/python3',
      autorestart: false,
      watch: false,
      max_memory_restart: '1G',
      cron_restart: '30 3 * * *',  // Runs at 9:00 AM IST (3:30 AM UTC) daily
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