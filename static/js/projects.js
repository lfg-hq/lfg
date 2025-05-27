document.addEventListener('DOMContentLoaded', function() {
    // Project dropdown functionality
    const dropdownButtons = document.querySelectorAll('.dropdown-button');
    
    dropdownButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.stopPropagation();
            const dropdown = this.closest('.dropdown');
            dropdown.classList.toggle('active');
        });
    });
    
    // Close dropdowns when clicking elsewhere
    document.addEventListener('click', function() {
        const activeDropdowns = document.querySelectorAll('.dropdown.active');
        activeDropdowns.forEach(dropdown => {
            dropdown.classList.remove('active');
        });
    });
    
    // Emoji picker functionality
    const emojiPicker = document.querySelector('.emoji-picker');
    const emojiInput = document.getElementById('project-icon');
    
    if (emojiPicker && emojiInput) {
        const emojiOptions = document.querySelectorAll('.emoji-option');
        
        emojiOptions.forEach(option => {
            option.addEventListener('click', function() {
                const emoji = this.textContent;
                emojiInput.value = emoji;
                
                // Update selected state
                emojiOptions.forEach(opt => opt.classList.remove('selected'));
                this.classList.add('selected');
            });
        });
    }
    
    // Delete project confirmation
    const deleteButtons = document.querySelectorAll('.delete-project-btn');
    
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const projectName = this.dataset.projectName;
            if (!confirm(`Are you sure you want to delete the project "${projectName}"? This action cannot be undone.`)) {
                e.preventDefault();
            }
        });
    });
    
    // Form validation for project creation
    const createProjectForm = document.getElementById('create-project-form');
    
    if (createProjectForm) {
        createProjectForm.addEventListener('submit', function(e) {
            const nameInput = document.getElementById('project-name');
            
            if (!nameInput.value.trim()) {
                e.preventDefault();
                
                // Create an error message if it doesn't exist
                let errorEl = document.getElementById('name-error');
                if (!errorEl) {
                    errorEl = document.createElement('div');
                    errorEl.id = 'name-error';
                    errorEl.className = 'alert alert-danger';
                    errorEl.textContent = 'Project name is required';
                    nameInput.parentNode.appendChild(errorEl);
                }
                
                nameInput.focus();
            }
        });
    }

    // Apply card hover effects
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-4px)';
            this.style.boxShadow = '0 0 15px rgba(99, 102, 241, 0.3)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = '';
        });
    });
    
    // Prevent click propagation on dropdown action buttons
    document.querySelectorAll('.dropdown-button').forEach(button => {
        button.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    });
}); 