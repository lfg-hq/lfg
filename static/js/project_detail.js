document.addEventListener('DOMContentLoaded', function() {    
    // Function to get CSRF token
    function getCSRFToken() {
        const csrfCookie = document.cookie
            .split(';')
            .find(cookie => cookie.trim().startsWith('csrftoken='));
        
        if (csrfCookie) {
            return csrfCookie.split('=')[1];
        }
        
        // Fallback to get token from form
        const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return csrfInput ? csrfInput.value : null;
    }
    
    // Debug: Check if the correct elements exist on page
    console.log('Debug: Conversation section exists:', historySection !== null);
    console.log('Debug: Messages container exists:', messagesContainer !== null);
    console.log('Debug: History title exists:', historyTitle !== null);
    console.log('Debug: Close button exists:', closeButton !== null);
}); 