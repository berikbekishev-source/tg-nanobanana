// Скрипт для выполнения в консоли браузера на странице Lava.top
// Откройте личный кабинет Lava.top и выполните этот код в консоли (F12)

// Ваш webhook URL
const WEBHOOK_URL = 'https://web-production-96df.up.railway.app/api/miniapp/lava-webhook';

// Функция отправки тестового вебхука
async function sendTestWebhook() {
    console.log('🚀 Отправка тестового вебхука...');

    // Тестовые данные платежа
    const testPayload = {
        id: 'test_webhook_' + Date.now(),
        type: 'payment',
        event: 'payment.success',
        test_mode: true,
        data: {
            order_id: 'test_order_' + Date.now(),
            amount: 5.00,
            currency: 'USD',
            status: 'success',
            payment_id: 'pay_test_123',
            customer: {
                email: 'test@example.com',
                phone: '+1234567890'
            },
            metadata: {
                tokens: 100,
                user_id: 'test_user'
            }
        },
        created_at: new Date().toISOString()
    };

    try {
        // Отправляем запрос на ваш webhook
        const response = await fetch(WEBHOOK_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Lava-Signature': 'test_signature',
                'X-Test-Mode': 'true'
            },
            body: JSON.stringify(testPayload)
        });

        if (response.ok) {
            console.log('✅ Webhook отправлен успешно!');
            console.log('Response:', await response.json());
        } else {
            console.log('❌ Ошибка:', response.status, response.statusText);
        }
    } catch (error) {
        console.log('❌ Ошибка отправки:', error);
        console.log('Возможно, нужно открыть CORS. Попробуйте альтернативный метод.');
    }
}

// Функция поиска кнопок тестирования на странице
function findTestButtons() {
    console.log('🔍 Поиск кнопок тестирования на странице...\n');

    const keywords = [
        'test', 'тест', 'webhook', 'вебхук',
        'send', 'отправить', 'ping', 'проверить',
        'sample', 'пример', 'debug', 'отладка'
    ];

    // Ищем все кнопки и ссылки
    const elements = document.querySelectorAll('button, a, [role="button"], .btn, .button');
    const found = [];

    elements.forEach(el => {
        const text = el.textContent.toLowerCase();
        const hasKeyword = keywords.some(keyword => text.includes(keyword));

        if (hasKeyword) {
            found.push({
                element: el,
                text: el.textContent.trim(),
                type: el.tagName
            });
        }
    });

    if (found.length > 0) {
        console.log(`✅ Найдено ${found.length} элементов для тестирования:\n`);
        found.forEach((item, index) => {
            console.log(`${index + 1}. [${item.type}] "${item.text}"`);
            console.log('   Element:', item.element);
        });
        console.log('\n💡 Попробуйте кликнуть на один из этих элементов');
    } else {
        console.log('❌ Кнопки тестирования не найдены автоматически');
        console.log('Попробуйте поискать вручную в разделах:');
        console.log('- Webhooks / Вебхуки');
        console.log('- API / Settings');
        console.log('- Developer Tools');
    }

    return found;
}

// Автоматический поиск API endpoints на странице
function findApiEndpoints() {
    console.log('\n🔍 Поиск API endpoints...\n');

    // Ищем в скриптах страницы
    const scripts = Array.from(document.scripts);
    const apiPatterns = [
        /api\.lava\.top/gi,
        /\/api\/v[12]\/webhook/gi,
        /\/test\/webhook/gi,
        /webhook\/test/gi
    ];

    scripts.forEach(script => {
        if (script.src || script.innerHTML) {
            const content = script.innerHTML || '';
            apiPatterns.forEach(pattern => {
                const matches = content.match(pattern);
                if (matches) {
                    console.log('📍 Найден endpoint:', matches[0]);
                }
            });
        }
    });
}

// Запуск всех проверок
console.log('═══════════════════════════════════════════');
console.log('   LAVA.TOP WEBHOOK TESTER');
console.log('═══════════════════════════════════════════\n');

// 1. Ищем кнопки на странице
const buttons = findTestButtons();

// 2. Ищем API endpoints
findApiEndpoints();

// 3. Предлагаем отправить тестовый webhook
console.log('\n═══════════════════════════════════════════');
console.log('Для отправки тестового вебхука выполните:');
console.log('> sendTestWebhook()');
console.log('═══════════════════════════════════════════');

// Делаем функцию доступной глобально
window.sendTestWebhook = sendTestWebhook;
window.testButtons = buttons;