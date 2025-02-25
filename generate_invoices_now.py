import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

from generate_invoices import generate_monthly_invoices

if __name__ == "__main__":
    generate_monthly_invoices() 