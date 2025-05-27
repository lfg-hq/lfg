#!/bin/bash

# Create directories if they don't exist
mkdir -p /app/static/css
mkdir -p /app/static/js
mkdir -p /app/staticfiles/css
mkdir -p /app/staticfiles/js

# Check if static files exist in the source directory
if [ -d "/app/static" ]; then
    echo "Copying static files to staticfiles directory..."
    cp -r /app/static/* /app/staticfiles/ 2>/dev/null || true
    echo "Static files copied."
else
    echo "Static directory not found."
fi

# Create placeholder files for missing static files to prevent 404 errors
for file in css/styles.css css/artifacts.css js/chat.js js/artifacts.js js/sidebar.js; do
    if [ ! -f "/app/staticfiles/$file" ]; then
        echo "Creating placeholder file for $file"
        mkdir -p "$(dirname "/app/staticfiles/$file")"
        
        if [[ "$file" == *.css ]]; then
            cat > "/app/staticfiles/$file" << EOF
/* 
 * Placeholder CSS file
 * This file was automatically generated to prevent 404 errors
 */
body {
    /* Empty rule */
}
EOF
        elif [[ "$file" == *.js ]]; then
            cat > "/app/staticfiles/$file" << EOF
/**
 * Placeholder JavaScript file
 * This file was automatically generated to prevent 404 errors
 */
console.log('Placeholder file loaded: ${file}');
EOF
        else
            touch "/app/staticfiles/$file"
        fi
    fi
done

# Set proper permissions
chmod -R 755 /app/staticfiles

# List the contents of the staticfiles directory
echo "Contents of staticfiles directory:"
ls -la /app/staticfiles/

# Check for specific files
echo "Checking for specific static files:"
for file in css/styles.css css/artifacts.css js/chat.js js/artifacts.js js/sidebar.js; do
    if [ -f "/app/staticfiles/$file" ]; then
        echo "✅ $file exists"
        echo "Content:"
        head -n 5 "/app/staticfiles/$file"
        echo ""
    else
        echo "❌ $file does not exist"
    fi
done 