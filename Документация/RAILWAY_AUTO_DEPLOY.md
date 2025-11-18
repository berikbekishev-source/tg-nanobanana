# Настройка автоматического деплоя Railway

## Проблема
Railway не задеплоил автоматически новый коммит `38899ac` после мержа в `main`.

## Решение

### 1. Проверка настроек Railway

Railway должен автоматически деплоить при пуше в подключенную ветку через GitHub integration. Проверьте:

1. **Откройте Railway Dashboard:**
   - https://railway.app/project/866bc61a-0ef1-41d1-af53-26784f6e5f06

2. **Проверьте настройки GitHub интеграции:**
   - Settings → Source → GitHub
   - Убедитесь что репозиторий `berikbekishev-source/tg-nanobanana` подключен
   - Проверьте что для production environment выбрана ветка `main`
   - Убедитесь что "Auto Deploy" включен

3. **Проверьте настройки сервисов:**
   - Каждый сервис (web, worker, beat) должен быть подключен к репозиторию
   - Root Directory должен быть правильным (обычно `/` или пусто)
   - Build Command и Start Command должны быть настроены правильно

### 2. GitHub Actions Workflow

Создан workflow `.github/workflows/deploy-production.yml` который:
- Запускается после успешного CI на ветке `main`
- Проверяет статус деплоя через Railway GraphQL API
- Ждет завершения деплоя всех сервисов
- Выполняет health check после деплоя

### 3. Ручная настройка (если автоматический деплой не работает)

Если Railway не деплоит автоматически:

1. **Проверьте Railway webhook в GitHub:**
   - Settings → Webhooks
   - Должен быть webhook от Railway
   - Проверьте что он активен и получает события `push`

2. **Запустите деплой вручную через Railway CLI:**
   ```bash
   export RAILWAY_TOKEN="47a20fbb-1f26-402d-8e66-ba38660ef1d4"
   railway login --token $RAILWAY_TOKEN
   railway link --project 866bc61a-0ef1-41d1-af53-26784f6e5f06
   railway up
   ```

3. **Или через Railway Dashboard:**
   - Откройте проект
   - Выберите production environment
   - Нажмите "Redeploy" для каждого сервиса

### 4. Проверка деплоя

После настройки проверьте что деплой работает:

1. **Сделайте тестовый коммит в main:**
   ```bash
   git checkout main
   echo "# Test" >> README.md
   git commit -m "test: check auto deploy"
   git push origin main
   ```

2. **Проверьте Railway Dashboard:**
   - Должен появиться новый деплой
   - Коммит должен совпадать с последним коммитом в main

3. **Проверьте GitHub Actions:**
   - После успешного CI должен запуститься `Deploy to Production (Railway)`
   - Workflow должен проверить статус деплоя и выполнить health check

### 5. Переменные окружения

Убедитесь что в GitHub Actions Variables настроены:
- `RAILWAY_API_TOKEN` - токен Railway API
- `PRODUCTION_BASE_URL` - URL production окружения

### 6. Troubleshooting

Если деплой все еще не работает автоматически:

1. **Проверьте логи Railway:**
   - Railway Dashboard → Deployments → View Logs
   - Ищите ошибки сборки или деплоя

2. **Проверьте GitHub webhook:**
   - GitHub → Settings → Webhooks
   - Проверьте последние доставки webhook от Railway
   - Убедитесь что события `push` доставляются успешно

3. **Переподключите репозиторий:**
   - Railway Dashboard → Settings → Source
   - Отключите и снова подключите GitHub репозиторий
   - Выберите правильную ветку для production environment

4. **Проверьте права доступа:**
   - Railway должен иметь доступ к репозиторию
   - GitHub App или Personal Access Token должны иметь правильные права

---

**После настройки:** Railway должен автоматически деплоить каждый коммит в `main` после успешного CI.

