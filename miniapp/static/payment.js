// Telegram Web App
const tg = window.Telegram.WebApp;

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    // Настройка Telegram Web App
    tg.ready();
    tg.expand();

    // Применить тему Telegram
    document.body.style.backgroundColor = tg.themeParams.bg_color || '#1a1a1a';

    // Получить данные пользователя
    const user = tg.initDataUnsafe.user;
    if (user) {
        console.log('User:', user);
    }

    // Инициализация элементов
    initPaymentForm();
});

function initPaymentForm() {
    const creditButtons = document.querySelectorAll('.credit-btn');
    const emailInput = document.getElementById('email');
    const payBtn = document.getElementById('payBtn');
    const totalAmount = document.getElementById('totalAmount');

    let selectedCredits = 100;
    let selectedPrice = 5;

    // Обработка выбора кредитов
    creditButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // Убрать активный класс со всех кнопок
            creditButtons.forEach(b => b.classList.remove('active'));

            // Добавить активный класс на выбранную кнопку
            btn.classList.add('active');

            // Получить данные
            selectedCredits = parseInt(btn.dataset.credits);
            selectedPrice = parseFloat(btn.dataset.price);

            // Обновить сумму
            totalAmount.textContent = selectedPrice;
        });
    });

    // Валидация email
    emailInput.addEventListener('input', () => {
        validateForm();
    });

    // Обработка нажатия на кнопку оплаты
    payBtn.addEventListener('click', async () => {
        const email = emailInput.value.trim();

        if (!validateEmail(email)) {
            tg.showAlert('Пожалуйста, введите корректный E-mail');
            return;
        }

        // Отключить кнопку
        payBtn.disabled = true;
        payBtn.textContent = 'Обработка...';

        try {
            // Отправить данные на сервер
            const response = await fetch('/api/miniapp/create-payment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    email: email,
                    credits: selectedCredits,
                    amount: selectedPrice,
                    currency: 'USD',
                    payment_method: 'card',
                    user_id: tg.initDataUnsafe.user?.id,
                    init_data: tg.initData
                })
            });

            const data = await response.json();

            if (data.success && data.payment_url) {
                // Открыть ссылку на оплату
                tg.openLink(data.payment_url);
            } else {
                tg.showAlert(data.error || 'Ошибка создания платежа');
                payBtn.disabled = false;
                payBtn.textContent = 'Оплатить';
            }
        } catch (error) {
            console.error('Error:', error);
            tg.showAlert('Произошла ошибка. Попробуйте еще раз.');
            payBtn.disabled = false;
            payBtn.textContent = 'Оплатить';
        }
    });

    // Начальная валидация
    validateForm();
}

function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function validateForm() {
    const emailInput = document.getElementById('email');
    const payBtn = document.getElementById('payBtn');
    const email = emailInput.value.trim();

    if (validateEmail(email)) {
        payBtn.disabled = false;
    } else {
        payBtn.disabled = true;
    }
}

// Обработка закрытия Web App
tg.onEvent('viewportChanged', () => {
    if (!tg.isExpanded) {
        tg.expand();
    }
});
