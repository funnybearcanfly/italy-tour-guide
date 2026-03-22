/**
 * 意大利旅游解说系统 - 主JavaScript文件
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all components
    initNavbar();
    initBackToTop();
    initSearch();
    initSmoothScroll();
    initLazyLoad();
});

/**
 * Navbar scroll effect
 */
function initNavbar() {
    const navbar = document.getElementById('mainNav');
    if (!navbar) return;

    window.addEventListener('scroll', function() {
        if (window.scrollY > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    });
}

/**
 * Back to top button
 */
function initBackToTop() {
    const btn = document.getElementById('backToTop');
    if (!btn) return;

    window.addEventListener('scroll', function() {
        if (window.scrollY > 300) {
            btn.classList.add('show');
        } else {
            btn.classList.remove('show');
        }
    });

    btn.addEventListener('click', function() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    });
}

/**
 * Search functionality
 */
function initSearch() {
    const form = document.getElementById('searchForm');
    const input = document.getElementById('searchInput');
    const modal = document.getElementById('searchModal');
    const results = document.getElementById('searchResults');

    if (!form || !input) return;

    let searchTimeout;

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        const query = input.value.trim();
        if (query.length < 2) return;

        // Show modal
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();

        // Show loading
        results.innerHTML = `
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">搜索中...</span>
                </div>
                <p class="mt-3 text-muted">正在搜索 "${query}"...</p>
            </div>
        `;

        // Fetch results
        fetch(`/api/search?q=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(data => {
                if (data.length === 0) {
                    results.innerHTML = `
                        <div class="text-center py-5">
                            <i class="bi bi-search fs-1 text-muted"></i>
                            <p class="mt-3 text-muted">没有找到相关内容</p>
                            <p class="small text-muted">尝试使用不同的关键词</p>
                        </div>
                    `;
                    return;
                }

                let html = '';
                data.forEach(item => {
                    html += `
                        <a href="/day/${item.day_num}" class="search-result-item text-decoration-none d-block">
                            <h6><i class="bi bi-calendar-day me-2"></i>${item.title}</h6>
                            <small class="text-muted">Day ${item.day_num}</small>
                        </a>
                    `;
                });
                results.innerHTML = html;
            })
            .catch(error => {
                results.innerHTML = `
                    <div class="text-center py-5 text-danger">
                        <i class="bi bi-exclamation-triangle fs-1"></i>
                        <p class="mt-3">搜索出错，请稍后重试</p>
                    </div>
                `;
            });
    });

    // Live search (optional)
    input.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        const query = this.value.trim();

        if (query.length < 3) return;

        searchTimeout = setTimeout(function() {
            // Could implement live search here
        }, 300);
    });
}

/**
 * Smooth scroll for anchor links
 */
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            if (href === '#') return;

            const target = document.querySelector(href);
            if (target) {
                e.preventDefault();
                const offset = 100; // Account for fixed navbar
                const targetPosition = target.getBoundingClientRect().top + window.scrollY - offset;

                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });
}

/**
 * Lazy load images
 */
function initLazyLoad() {
    const images = document.querySelectorAll('img[data-src]');

    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.removeAttribute('data-src');
                    observer.unobserve(img);
                }
            });
        }, {
            rootMargin: '50px 0px'
        });

        images.forEach(img => imageObserver.observe(img));
    } else {
        // Fallback for older browsers
        images.forEach(img => {
            img.src = img.dataset.src;
            img.removeAttribute('data-src');
        });
    }
}

/**
 * Reading progress indicator (optional)
 */
function initReadingProgress() {
    const progressBar = document.querySelector('.reading-progress');
    if (!progressBar) return;

    window.addEventListener('scroll', function() {
        const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
        const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
        const scrolled = (winScroll / height) * 100;
        progressBar.style.width = scrolled + '%';
    });
}

/**
 * Copy code blocks
 */
function initCodeCopy() {
    document.querySelectorAll('pre code').forEach(block => {
        const button = document.createElement('button');
        button.className = 'btn btn-sm btn-outline-secondary position-absolute top-0 end-0 m-2';
        button.innerHTML = '<i class="bi bi-clipboard"></i>';
        button.title = '复制代码';

        button.addEventListener('click', function() {
            navigator.clipboard.writeText(block.textContent).then(() => {
                button.innerHTML = '<i class="bi bi-check"></i>';
                setTimeout(() => {
                    button.innerHTML = '<i class="bi bi-clipboard"></i>';
                }, 2000);
            });
        });

        block.parentElement.style.position = 'relative';
        block.parentElement.appendChild(button);
    });
}

/**
 * Table of Contents generation
 */
function generateTOC() {
    const article = document.querySelector('.article-content');
    const tocList = document.querySelector('.toc-list');

    if (!article || !tocList) return;

    const headings = article.querySelectorAll('h2, h3');

    headings.forEach((heading, index) => {
        const id = `heading-${index}`;
        heading.id = id;

        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = `#${id}`;
        a.textContent = heading.textContent;

        if (heading.tagName === 'H3') {
            li.className = 'toc-h3';
        }

        li.appendChild(a);
        tocList.appendChild(li);
    });
}

/**
 * Image lightbox (simple implementation)
 */
function initLightbox() {
    const images = document.querySelectorAll('.article-content img');

    images.forEach(img => {
        img.style.cursor = 'zoom-in';
        img.addEventListener('click', function() {
            // Create lightbox
            const lightbox = document.createElement('div');
            lightbox.className = 'lightbox';
            lightbox.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.9);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 9999;
                cursor: zoom-out;
            `;

            const imgClone = document.createElement('img');
            imgClone.src = this.src;
            imgClone.style.cssText = `
                max-width: 90%;
                max-height: 90%;
                object-fit: contain;
            `;

            lightbox.appendChild(imgClone);
            document.body.appendChild(lightbox);

            lightbox.addEventListener('click', function() {
                document.body.removeChild(lightbox);
            });
        });
    });
}

/**
 * Scroll spy for navigation
 */
function initScrollSpy() {
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.day-navigation .nav-link');

    if (sections.length === 0 || navLinks.length === 0) return;

    window.addEventListener('scroll', function() {
        let current = '';
        const offset = 150;

        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.clientHeight;

            if (window.scrollY >= sectionTop - offset) {
                current = section.getAttribute('id');
            }
        });

        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === `#${current}`) {
                link.classList.add('active');
            }
        });
    });
}

// Call additional initializations
document.addEventListener('DOMContentLoaded', function() {
    generateTOC();
    initLightbox();
    initScrollSpy();
});
