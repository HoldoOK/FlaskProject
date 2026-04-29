// static/js/theme.js

document.addEventListener('DOMContentLoaded', function () {
    const STORAGE_KEY = 'shopflask-theme';
    const html = document.documentElement;
    const toggleBtn = document.getElementById('themeToggle');
    const lightIcon = document.querySelector('.theme-icon-light');
    const darkIcon = document.querySelector('.theme-icon-dark');

    // Определяем сохранённую или системную тему
    function getPreferredTheme() {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) return saved;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    // Обновляем иконку
    function updateIcon(theme) {
        if (!lightIcon || !darkIcon) return;
        if (theme === 'dark') {
            lightIcon.classList.add('d-none');
            darkIcon.classList.remove('d-none');
        } else {
            lightIcon.classList.remove('d-none');
            darkIcon.classList.add('d-none');
        }
    }

    // Применяем тему
    function applyTheme(theme) {
        html.setAttribute('data-bs-theme', theme);
        localStorage.setItem(STORAGE_KEY, theme);
        updateIcon(theme);
    }

    // Переключение
    function toggleTheme() {
        const current = html.getAttribute('data-bs-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next);
    }

    // Применяем тему сразу при загрузке
    applyTheme(getPreferredTheme());

    // Вешаем обработчик клика
    if (toggleBtn) {
        toggleBtn.addEventListener('click', function (e) {
            e.preventDefault();
            toggleTheme();
        });
    }

    // Слушаем смену системной темы
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
        if (!localStorage.getItem(STORAGE_KEY)) {
            applyTheme(e.matches ? 'dark' : 'light');
        }
    });
});