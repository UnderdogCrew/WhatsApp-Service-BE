#!/bin/bash

echo "🔄 Generating OpenAPI schema..."
python3 -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
import django
django.setup()

from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg import openapi
import json

# Generate the schema
generator = OpenAPISchemaGenerator(
    info=openapi.Info(
        title='WhatsApp Service API',
        default_version='v1',
        description='Comprehensive API documentation for WhatsApp Business Platform integration',
        terms_of_service='https://privacy-policy.theunderdogcrew.com/',
        contact=openapi.Contact(email='hello@theunderdogcrew.com'),
        license=openapi.License(name='BSD License'),
    ),
    version='v1',
    url='https://whatsapp-api.theunderdogcrew.com'
)

schema = generator.get_schema()
schema_dict = schema.as_odict()

# Optionally filter to a specific path if DOCS_PATH_FILTER is set
path_filter = os.environ.get('DOCS_PATH_FILTER')
if path_filter:
    if 'paths' in schema_dict and path_filter in schema_dict['paths']:
        schema_dict['paths'] = {
            path_filter: schema_dict['paths'][path_filter]
        }
    else:
        raise SystemExit(f'Path {path_filter} not found in schema')

# Save as JSON
with open('openapi-schema.json', 'w') as f:
    json.dump(schema_dict, f, indent=2)

print('✅ OpenAPI schema generated: openapi-schema.json')
"

echo "📝 Generating HTML documentation with Redocly..."
npx @redocly/cli build-docs openapi-schema.json --output docs/index.html

echo "✅ Documentation generated successfully!"
echo "📖 View your documentation at: http://localhost:8001/"
echo "🔄 Or regenerate docs by running: ./generate-docs.sh"
