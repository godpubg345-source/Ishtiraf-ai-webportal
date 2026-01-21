/**
 * IshtirafAI Web Portal - Main JavaScript
 * Utility functions and UI enhancements
 */

(function () {
    'use strict';

    // ============================================
    // DOM Ready
    // ============================================
    document.addEventListener('DOMContentLoaded', function () {
        initFlashMessages();
        initFormValidation();
        initAnimations();
        console.log('IshtirafAI: JS Loaded ✓');
    });

    // ============================================
    // Flash Messages (Auto-dismiss)
    // ============================================
    function initFlashMessages() {
        const alerts = document.querySelectorAll('.alert[data-autodismiss]');
        alerts.forEach(function (alert) {
            const delay = parseInt(alert.dataset.autodismiss) || 5000;
            setTimeout(function () {
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-20px)';
                setTimeout(function () {
                    alert.remove();
                }, 300);
            }, delay);
        });
    }

    // ============================================
    // Form Validation
    // ============================================
    function initFormValidation() {
        const forms = document.querySelectorAll('form[data-validate]');
        forms.forEach(function (form) {
            form.addEventListener('submit', function (e) {
                let isValid = true;
                const requiredFields = form.querySelectorAll('[required]');

                requiredFields.forEach(function (field) {
                    if (!field.value.trim()) {
                        isValid = false;
                        field.classList.add('is-invalid');
                        showFieldError(field, 'This field is required');
                    } else {
                        field.classList.remove('is-invalid');
                        hideFieldError(field);
                    }
                });

                // Email validation
                const emailFields = form.querySelectorAll('input[type="email"]');
                emailFields.forEach(function (field) {
                    if (field.value && !isValidEmail(field.value)) {
                        isValid = false;
                        field.classList.add('is-invalid');
                        showFieldError(field, 'Please enter a valid email');
                    }
                });

                if (!isValid) {
                    e.preventDefault();
                }
            });
        });
    }

    function showFieldError(field, message) {
        hideFieldError(field);
        const errorDiv = document.createElement('div');
        errorDiv.className = 'field-error text-danger mt-1';
        errorDiv.style.fontSize = '0.85rem';
        errorDiv.textContent = message;
        field.parentNode.appendChild(errorDiv);
    }

    function hideFieldError(field) {
        const existing = field.parentNode.querySelector('.field-error');
        if (existing) existing.remove();
    }

    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    // ============================================
    // AJAX Request Wrapper
    // ============================================
    window.IshtirafAPI = {
        request: function (url, options) {
            options = options || {};
            options.headers = options.headers || {};
            options.headers['Content-Type'] = 'application/json';

            return fetch(url, options)
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('HTTP ' + response.status);
                    }
                    return response.json();
                })
                .catch(function (error) {
                    console.error('API Error:', error);
                    throw error;
                });
        },

        get: function (url) {
            return this.request(url, { method: 'GET' });
        },

        post: function (url, data) {
            return this.request(url, {
                method: 'POST',
                body: JSON.stringify(data)
            });
        }
    };

    // ============================================
    // Toast Notifications
    // ============================================
    window.IshtirafToast = {
        show: function (message, type) {
            type = type || 'info';
            const toast = document.createElement('div');
            toast.className = 'toast alert alert-' + type + ' animate-fadeIn';
            toast.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;min-width:300px;';
            toast.textContent = message;

            document.body.appendChild(toast);

            setTimeout(function () {
                toast.style.opacity = '0';
                setTimeout(function () { toast.remove(); }, 300);
            }, 4000);
        },

        success: function (msg) { this.show(msg, 'success'); },
        error: function (msg) { this.show(msg, 'danger'); },
        warning: function (msg) { this.show(msg, 'warning'); },
        info: function (msg) { this.show(msg, 'info'); }
    };

    // ============================================
    // Animations
    // ============================================
    function initAnimations() {
        // Fade in cards on load
        const cards = document.querySelectorAll('.card');
        cards.forEach(function (card, index) {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            setTimeout(function () {
                card.style.transition = 'all 0.3s ease';
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 100 * index);
        });
    }

    // ============================================
    // Utility Functions
    // ============================================
    window.IshtirafUtils = {
        formatDate: function (dateStr) {
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
        },

        formatRisk: function (score) {
            if (score >= 7) return { level: 'High', class: 'danger' };
            if (score >= 4) return { level: 'Medium', class: 'warning' };
            return { level: 'Low', class: 'success' };
        },

        debounce: function (func, wait) {
            var timeout;
            return function () {
                var context = this, args = arguments;
                clearTimeout(timeout);
                timeout = setTimeout(function () {
                    func.apply(context, args);
                }, wait);
            };
        },

        copyToClipboard: function (text) {
            if (navigator.clipboard) {
                navigator.clipboard.writeText(text).then(function () {
                    IshtirafToast.success('Copied to clipboard!');
                });
            }
        }
    };

    // ============================================
    // Confirmation Dialogs
    // ============================================
    window.IshtirafConfirm = function (message, callback) {
        if (confirm(message)) {
            callback();
        }
    };

    // ============================================
    // Loading Spinner
    // ============================================
    window.IshtirafLoader = {
        show: function () {
            var loader = document.getElementById('global-loader');
            if (!loader) {
                loader = document.createElement('div');
                loader.id = 'global-loader';
                loader.innerHTML = '<div class="spinner"></div>';
                loader.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:9999;';
                loader.querySelector('.spinner').style.cssText = 'width:50px;height:50px;border:4px solid #fff;border-top-color:#1f6aa5;border-radius:50%;animation:spin 1s linear infinite;';

                var style = document.createElement('style');
                style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
                document.head.appendChild(style);

                document.body.appendChild(loader);
            }
            loader.style.display = 'flex';
        },

        hide: function () {
            var loader = document.getElementById('global-loader');
            if (loader) {
                loader.style.display = 'none';
            }
        }
    };

    // ============================================
    // Table Search Filter
    // ============================================
    window.IshtirafSearch = {
        init: function (inputSelector, tableSelector) {
            var input = document.querySelector(inputSelector);
            var table = document.querySelector(tableSelector);

            if (!input || !table) return;

            input.addEventListener('keyup', IshtirafUtils.debounce(function () {
                var filter = input.value.toLowerCase();
                var rows = table.querySelectorAll('tbody tr');

                rows.forEach(function (row) {
                    var text = row.textContent.toLowerCase();
                    if (text.indexOf(filter) > -1) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                });
            }, 300));
        }
    };

    // ============================================
    // CSV Export
    // ============================================
    window.IshtirafExport = {
        tableToCSV: function (tableSelector, filename) {
            var table = document.querySelector(tableSelector);
            if (!table) {
                IshtirafToast.error('Table not found');
                return;
            }

            var csv = [];
            var rows = table.querySelectorAll('tr');

            rows.forEach(function (row) {
                var cols = row.querySelectorAll('td, th');
                var rowData = [];

                cols.forEach(function (col) {
                    // Clean text and escape quotes
                    var text = col.innerText.replace(/"/g, '""').trim();
                    rowData.push('"' + text + '"');
                });

                csv.push(rowData.join(','));
            });

            // Download
            var csvContent = csv.join('\n');
            var blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            var link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = filename || 'export.csv';
            link.click();

            IshtirafToast.success('CSV exported successfully!');
        },

        usersToCSV: function () {
            this.tableToCSV('table', 'ishtirafai_users_' + new Date().toISOString().slice(0, 10) + '.csv');
        },

        patientsToCSV: function () {
            this.tableToCSV('table', 'ishtirafai_patients_' + new Date().toISOString().slice(0, 10) + '.csv');
        }
    };

    // ============================================
    // Auto-init Search on Admin Pages
    // ============================================
    document.addEventListener('DOMContentLoaded', function () {
        // Init search on admin dashboard
        var searchInput = document.querySelector('input[placeholder*="Search"]');
        if (searchInput) {
            IshtirafSearch.init('input[placeholder*="Search"]', 'table');
        }
    });

})();
