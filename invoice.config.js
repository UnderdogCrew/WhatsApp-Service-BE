module.exports = {
  apps: [
    {
      name: 'whatsapp-invoice-generator',
      script: 'generate_invoices.py',
      interpreter: '/opt/whatsapp_service/enve/bin/python3',
      autorestart: false,
      watch: false,
      max_memory_restart: '1G',
      cron_restart: '30 2 1 * *',  // 2:30 AM UTC = 8:00 AM IST
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