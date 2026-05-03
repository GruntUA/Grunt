# Ґрунт Framework

Metadata-driven application framework для побудови CMS, ERP, реєстрів та інших бізнес-додатків.

## Швидкий старт (Development)

Проєкт використовує **mise** для керування залежностями та задачами прямо з кореня репозиторію.

### 1. Встановлення інструментів (одноразово)
Встановіть `mise`:
```bash
curl https://mise.run | sh
# Додайте активацію у ваш ~/.bashrc
echo 'eval "$(/home/maks4/.local/bin/mise activate bash)"' >> ~/.bashrc
source ~/.bashrc
```

### 2. Розгортання проєкту з 0
Склонуйте репозиторій та запустіть підготовку прямо з кореня:
```bash
git clone https://github.com/rareMaxim/grunt && cd grunt

# Встановлення рантаймів, пакетів та ініціалізація БД
mise run setup
```

### 3. Запуск
```bash
# Запуск backend та frontend паралельно (працює з будь-якої папки проєкту)
mise dev
```

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs

---

## Основні команди (через `mise`)

Використовуйте `mise tasks` для повного списку. Всі команди автоматично виконуються у правильних піддиректоріях.

| Команда | Опис |
|---------|------|
| `mise dev` | Backend + Frontend паралельно |
| `mise test` | Всі тести (Python + Vitest) |
| `mise lint` | Перевірка коду (Ruff + ESLint) |
| `mise migrate`| Застосувати міграції БД |
| `mise db-reset`| Скинути БД до початкового стану |

---

## Структура проєкту

```
my-project/         # Корінь project
├── apps/grunt/     # Framework app
│   ├── grunt/      # Python package / FastAPI backend
│   └── frontend/   # Vue 3 / TypeScript frontend
├── sites/          # Site instances
└── ...
```
