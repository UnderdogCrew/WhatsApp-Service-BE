module.exports = {
  apps: [
    {
      name: 'whatsapp-invoice-generator',
      script: 'generate_invoices.py',
      interpreter: '/opt/whatsapp_service/enve/bin/python3',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      cron_restart: '0 8 1 * *',  // Runs at 8:00 AM on the 1st day of every month
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