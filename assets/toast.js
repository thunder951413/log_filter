// Toast Notification System
class ToastManager {
    constructor() {
        this.container = null;
        this.toasts = new Map();
        this.init();
    }

    init() {
        this.container = document.getElementById('toast-container');
        if (!this.container) {
            console.error('Toast container not found');
            return;
        }
    }

    show(message, type = 'info', duration = 4000) {
        if (!this.container) {
            console.warn('Toast container not initialized');
            return;
        }

        const toastId = 'toast-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        const toast = this.createToast(toastId, message, type);
        
        this.container.appendChild(toast);
        this.toasts.set(toastId, toast);

        // Trigger animation
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);

        // Auto remove
        if (duration > 0) {
            setTimeout(() => {
                this.hide(toastId);
            }, duration);
        }

        return toastId;
    }

    createToast(id, message, type) {
        const toast = document.createElement('div');
        toast.id = id;
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-content">
                <span class="toast-message">${this.escapeHtml(message)}</span>
                <button class="toast-close" onclick="toastManager.hide('${id}')">&times;</button>
            </div>
        `;
        
        // Add progress bar for timed toasts
        if (type !== 'error') { // Don't auto-hide errors
            const progressBar = document.createElement('div');
            progressBar.className = 'toast-progress';
            toast.appendChild(progressBar);
        }
        
        return toast;
    }

    hide(toastId) {
        const toast = this.toasts.get(toastId);
        if (!toast) return;

        toast.classList.remove('show');
        toast.classList.add('hide');

        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
            this.toasts.delete(toastId);
        }, 300);
    }

    hideAll() {
        this.toasts.forEach((toast, id) => {
            this.hide(id);
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize global toast manager
window.toastManager = new ToastManager();

// Dash integration function
window.showToast = function(message, type = 'info', duration = 4000) {
    if (window.toastManager) {
        return window.toastManager.show(message, type, duration);
    }
    console.warn('Toast manager not available');
};

// CSS for toast content and progress bar
const toastStyles = `
.toast-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
}

.toast-message {
    flex: 1;
    line-height: 1.4;
}

.toast-close {
    background: none;
    border: none;
    color: inherit;
    font-size: 18px;
    cursor: pointer;
    padding: 0;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0.7;
    transition: opacity 0.2s;
}

.toast-close:hover {
    opacity: 1;
}

.toast-progress {
    position: absolute;
    bottom: 0;
    left: 0;
    height: 3px;
    background: rgba(255, 255, 255, 0.3);
    border-radius: 0 0 12px 12px;
    animation: toast-progress 4s linear;
}

@keyframes toast-progress {
    from { width: 100%; }
    to { width: 0%; }
}

.toast.hide {
    opacity: 0;
    transform: translateX(400px);
}

/* Icon styles for different toast types */
.toast::before {
    content: '';
    position: absolute;
    left: 16px;
    top: 50%;
    transform: translateY(-50%);
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: bold;
}

.toast-success::before {
    content: '✓';
}

.toast-error::before {
    content: '✕';
}

.toast-warning::before {
    content: '!';
}

.toast-info::before {
    content: 'i';
}

/* Add padding for icon */
.toast {
    padding-left: 52px;
}
`;

// Inject additional styles
const styleSheet = document.createElement('style');
styleSheet.textContent = toastStyles;
document.head.appendChild(styleSheet);