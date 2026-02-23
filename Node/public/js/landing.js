document.addEventListener('DOMContentLoaded', () => {
    // Header scroll effect
    const header = document.querySelector('header');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 100) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
    });

    // Animate the airplane path
    const airplane = document.querySelector('.airplane');
    
    function updateAirplanePath() {
        const time = Date.now() * 0.001;
        const x = Math.sin(time * 0.5) * 60;
        const y = Math.cos(time * 0.3) * 30 - 20;
        
        if (airplane) {
            airplane.style.transform = `translate(${x}px, ${y}px) rotate(${x * 0.5}deg)`;
        }
        
        requestAnimationFrame(updateAirplanePath);
    }
    
    updateAirplanePath();
    
    // Add reveal animations for sections
    const revealElements = document.querySelectorAll('.feature-card, .step, .showcase-item, .pricing-card');
    
    function checkReveal() {
        const windowHeight = window.innerHeight;
        const revealPoint = 150;
        
        revealElements.forEach(element => {
            const revealTop = element.getBoundingClientRect().top;
            
            if (revealTop < windowHeight - revealPoint) {
                element.classList.add('revealed');
            }
        });
    }
    
    // Initial check
    checkReveal();
    
    // Check on scroll
    window.addEventListener('scroll', checkReveal);
    
    // Particle animation
    const particles = document.querySelectorAll('.particle');
    
    particles.forEach(particle => {
        // Random initial position
        const x = Math.random() * 100 - 50;
        const y = Math.random() * 100 - 50;
        particle.style.transform = `translate(${x}px, ${y}px)`;
    });
}); 