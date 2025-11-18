# Настройка автоматического деплоя Railway

## Текущий статус

✅ Workflow `deploy-production.yml` создан и добавлен в PR #106
✅ `RAILWAY_API_TOKEN` обновлен в GitHub Variables
✅ `PRODUCTION_BASE_URL` настроен
⚠️ Railway не деплоит автоматически (задеплоен старый коммит `a4c9a38` вместо `38899ac`)

## Проблема

Railway не получает уведомления о новых коммитах в `main` или Auto Deploy не включен.

## Решение: Настройка Railway через Dashboard

### Шаг 1: Проверка GitHub Integration

1. Откройте Railway Dashboard:
   https://railway.app/project/866bc61a-0ef1-41d1-af53-26784f6e5f06

2. Перейдите в **Settings → Source → GitHub**

3. Убедитесь что:
   - ✅ GitHub аккаунт подключен
   - ✅ Репозиторий `berikbekishev-source/tg-nanobanana` выбран
   - ✅ Для **production** environment (`2eee50d8-402e-44bf-9035-8298efef91bc`):
     - Branch: `main`
     - Root Directory: `/` (или пусто)
     - **Auto Deploy: ВКЛЮЧЕН** ✅

### Шаг 2: Настройка каждого сервиса

Для каждого сервиса (`web`, `worker`, `beat`):

1. Выберите сервис в Railway Dashboard
2. Перейдите в **Settings → Source**
3. Убедитесь что:
   - ✅ GitHub репозиторий подключен
   - ✅ Branch: `main`
   - ✅ **Auto Deploy: ВКЛЮЧЕН** ✅

### Шаг 3: Проверка GitHub Webhooks

1. Откройте GitHub репозиторий:
   https://github.com/berikbekishev-source/tg-nanobanana

2. Перейдите в **Settings → Webhooks**

3. Найдите webhook от Railway (обычно URL содержит `railway.app`)

4. Убедитесь что:
   - ✅ Webhook активен
   - ✅ События включают `push`
   - ✅ Последние доставки успешны (зеленые галочки)

5. Если webhook отсутствует или не работает:
   - Railway должен создать его автоматически при подключении GitHub
   - Или создайте вручную через Railway Dashboard → Settings → Source → GitHub

### Шаг 4: Проверка после настройки

После настройки Railway должен автоматически задеплоить новый коммит при пуше в `main`.

Проверьте:
```bash
# Проверка статуса деплоя
export RAILWAY_TOKEN="db1ab228-ea97-48b8-afda-b0a24943dd7e"
railway status --json | jq '.services.edges[].node.serviceInstances.edges[] | select(.node.environmentId=="2eee50d8-402e-44bf-9035-8298efef91bc") | {serviceName, commit: .node.latestDeployment.meta.commitHash[0:7], status: .node.latestDeployment.status}'
```

## Как работает автоматический деплой

1. **Push в `main`** → GitHub отправляет webhook в Railway
2. **Railway получает webhook** → Запускает автоматический деплой (если Auto Deploy включен)
3. **GitHub Actions CI** → Запускается workflow `CI` на коммите
4. **После успешного CI** → Запускается workflow `Deploy to Production (Railway)`
5. **Workflow мониторит деплой** → Проверяет статус через Railway GraphQL API
6. **Health Check** → Проверяет `/api/health` после деплоя
7. **Post Deploy Monitor** → Дополнительная проверка логов и health endpoint

## Troubleshooting

### Railway не деплоит автоматически

1. Проверьте что Auto Deploy включен для production environment
2. Проверьте что branch установлен на `main`
3. Проверьте GitHub webhooks (последние доставки)
4. Проверьте логи Railway (может быть ошибка сборки)

### Workflow не запускается

1. Проверьте что workflow `CI` успешно завершился
2. Проверьте что переменные `RAILWAY_API_TOKEN` и `PRODUCTION_BASE_URL` настроены
3. Проверьте логи workflow в GitHub Actions

### Деплой не завершается

1. Проверьте логи Railway (может быть ошибка сборки/деплоя)
2. Проверьте health endpoint: `curl https://web-production-96df.up.railway.app/api/health`
3. Проверьте логи сервисов через Railway Dashboard

---

**Дата создания:** 2025-11-18
**Последнее обновление:** 2025-11-18
