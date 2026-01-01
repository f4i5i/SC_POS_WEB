"""
PythonAnywhere WSGI Configuration File

INSTRUCTIONS:
1. Copy this entire content
2. Go to Web tab on PythonAnywhere
3. Click on your WSGI configuration file link
4. Replace all content with this
5. Change 'yourusername' to your actual username (3 places)
6. Save and reload web app
"""

import sys
import os

# ============================================
# CHANGE 'yourusername' TO YOUR ACTUAL USERNAME
# ============================================
USERNAME = 'f4i5i'  # <-- CHANGE THIS!
# ============================================

# Project path
project_home = f'/home/{USERNAME}/SOC_WEB_APP'

# Add to path
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables
os.environ['FLASK_ENV'] = 'production'
os.environ['SECRET_KEY'] = 'sc-pos-2024-xK9mN3pQ7vR2wY5zA8bC1dE4fG6hJ0kL'
os.environ['DATABASE_URL'] = f'sqlite:////home/{USERNAME}/SOC_WEB_APP/instance/pos.db'

# Business Configuration
os.environ['BUSINESS_NAME'] = 'Sunnat Collection'
os.environ['BUSINESS_ADDRESS'] = 'Mall of Wah, Pakistan'
os.environ['CURRENCY_SYMBOL'] = 'Rs.'

# Import and create Flask app
from app import create_app

application = create_app('production')

# Ensure instance folder exists
instance_path = os.path.join(project_home, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)
