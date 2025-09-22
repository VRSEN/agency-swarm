# Лучшие практики Agency Swarm

Этот документ содержит проверенные паттерны, рекомендации и лучшие практики для разработки эффективных многоагентных систем на Agency Swarm.

## Содержание

1. [Архитектурные паттерны](#архитектурные-паттерны)
2. [Дизайн агентов](#дизайн-агентов)
3. [Система инструментов](#система-инструментов)
4. [Управление состоянием](#управление-состоянием)
5. [Обработка ошибок](#обработка-ошибок)
6. [Тестирование](#тестирование)
7. [Производительность](#производительность)
8. [Безопасность](#безопасность)

---

## Архитектурные паттерны

### 1. Паттерн "Оркестратор-Исполнители"

**✅ Рекомендуется:**
```python
# Четкое разделение ролей
coordinator = Agent(
    name="TaskCoordinator",
    instructions="""
    Ты координатор задач. Твоя роль:
    1. Анализируй входящие запросы
    2. Разбивай сложные задачи на подзадачи
    3. Делегируй работу специализированным агентам
    4. Собирай результаты и формируй финальный ответ
    
    НЕ выполняй специализированные задачи сам - делегируй их.
    """
)

specialist = Agent(
    name="DataSpecialist", 
    instructions="""
    Ты специалист по работе с данными. Твоя роль:
    1. Обрабатывай данные с помощью своих инструментов
    2. Возвращай структурированные результаты
    3. Фокусируйся только на задачах обработки данных
    """
)
```

**❌ Избегайте:**
```python
# Размытые роли и ответственности
general_agent = Agent(
    name="GeneralAgent",
    instructions="Делай всё что попросят"  # Слишком общее
)
```

### 2. Паттерн "Конвейер обработки"

```python
# Последовательная обработка данных
agency = Agency(
    input_processor,
    communication_flows=[
        input_processor > data_validator,
        data_validator > data_transformer,
        data_transformer > output_formatter
    ]
)
```

### 3. Паттерн "Экспертная система"

```python
# Разные эксперты для разных областей
agency = Agency(
    consultant,
    communication_flows=[
        consultant > legal_expert,
        consultant > financial_expert,
        consultant > technical_expert
    ]
)
```

---

## Дизайн агентов

### 1. Принцип единственной ответственности

**✅ Хорошо:**
```python
class EmailAgent(Agent):
    def __init__(self):
        super().__init__(
            name="EmailAgent",
            instructions="""
            Ты специалист по email-маркетингу. Твои задачи:
            1. Создавай email-кампании
            2. Анализируй метрики email-рассылок
            3. Оптимизируй subject lines
            4. Сегментируй аудиторию для рассылок
            
            НЕ занимайся социальными сетями или другими каналами.
            """,
            tools=[create_email_campaign, analyze_email_metrics]
        )
```

**❌ Плохо:**
```python
class MarketingAgent(Agent):
    def __init__(self):
        super().__init__(
            name="MarketingAgent",
            instructions="Занимайся всем маркетингом",  # Слишком широко
            tools=[email_tool, social_tool, seo_tool, ads_tool]  # Слишком много
        )
```

### 2. Четкие и конкретные инструкции

**✅ Хорошо:**
```python
instructions = """
Ты аналитик данных. Когда получаешь запрос на анализ:

1. ВСЕГДА сначала используй load_data для загрузки данных
2. Проверь качество данных с помощью validate_data
3. Выполни анализ с помощью analyze_data
4. Создай визуализацию с помощью create_chart
5. Сформулируй выводы в структурированном виде

Пример рабочего процесса:
- Пользователь: "Проанализируй продажи"
- Ты: load_data("sales_db") → validate_data() → analyze_data("trend") → create_chart("line")

НИКОГДА не анализируй данные без их предварительной загрузки и валидации.
"""
```

**❌ Плохо:**
```python
instructions = "Анализируй данные как считаешь нужным"
```

### 3. Использование примеров в инструкциях

```python
instructions = """
Ты переводчик документов. Процесс работы:

1. Определи язык исходного документа
2. Переведи текст на целевой язык
3. Проверь качество перевода
4. Отформатируй результат

Примеры:
- Запрос: "Переведи этот текст на английский: Привет, мир!"
- Ответ: "Исходный язык: русский. Перевод: Hello, world!"

- Запрос: "Translate to Russian: Good morning"  
- Ответ: "Source language: English. Translation: Доброе утро"

Всегда указывай исходный язык в ответе.
"""
```

### 4. Структурированные выходы

```python
from pydantic import BaseModel, Field

class AnalysisResult(BaseModel):
    status: str = Field(..., description="Статус анализа: success/error")
    summary: str = Field(..., description="Краткое резюме")
    metrics: dict = Field(..., description="Ключевые метрики")
    recommendations: list[str] = Field(..., description="Рекомендации")

analyst = Agent(
    name="Analyst",
    instructions="Возвращай результаты в структурированном виде",
    output_type=AnalysisResult
)
```

---

## Система инструментов

### 1. Принципы создания инструментов

**✅ Хорошие инструменты:**
```python
@function_tool
async def calculate_roi(
    investment: float = Field(..., gt=0, description="Сумма инвестиций в рублях"),
    revenue: float = Field(..., gt=0, description="Полученная выручка в рублях"),
    period_months: int = Field(..., gt=0, le=120, description="Период в месяцах (1-120)")
) -> str:
    """
    Рассчитывает ROI (возврат инвестиций) за указанный период.
    
    Формула: ROI = ((Выручка - Инвестиции) / Инвестиции) * 100%
    
    Примеры:
    - calculate_roi(100000, 150000, 12) -> "ROI: 50.0% за 12 месяцев"
    - calculate_roi(50000, 45000, 6) -> "ROI: -10.0% за 6 месяцев (убыток)"
    
    Args:
        investment: Сумма первоначальных инвестиций
        revenue: Полученная выручка
        period_months: Период расчета в месяцах
        
    Returns:
        Строка с результатом расчета ROI
    """
    roi = ((revenue - investment) / investment) * 100
    status = "прибыль" if roi > 0 else "убыток" if roi < 0 else "безубыточность"
    
    return f"ROI: {roi:.1f}% за {period_months} месяцев ({status})"
```

**❌ Плохие инструменты:**
```python
@function_tool
def do_calculation(data: str) -> str:  # Неясное назначение
    """Does some calculation."""  # Плохое описание
    return "result"  # Неинформативный результат
```

### 2. Валидация входных данных

```python
from pydantic import BaseModel, Field, field_validator

class EmailData(BaseModel):
    email: str = Field(..., description="Email адрес получателя")
    subject: str = Field(..., min_length=1, max_length=100, description="Тема письма")
    body: str = Field(..., min_length=10, description="Текст письма")
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError("Некорректный email адрес")
        return v
    
    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Тема письма не может быть пустой")
        return v.strip()

@function_tool
async def send_email(email_data: EmailData) -> str:
    """Отправляет email с валидацией данных."""
    # Логика отправки
    return f"Email отправлен на {email_data.email}"
```

### 3. Обработка ошибок в инструментах

```python
@function_tool
async def fetch_api_data(
    url: str = Field(..., description="URL для запроса"),
    timeout: int = Field(30, gt=0, le=300, description="Таймаут в секундах")
) -> str:
    """Безопасно получает данные из API."""
    
    try:
        import aiohttp
        import asyncio
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.text()
                    return f"Данные получены успешно. Размер: {len(data)} символов"
                else:
                    return f"Ошибка API: HTTP {response.status}"
                    
    except asyncio.TimeoutError:
        return f"Таймаут при запросе к {url} (>{timeout}с)"
    except aiohttp.ClientError as e:
        return f"Ошибка соединения: {str(e)}"
    except Exception as e:
        return f"Неожиданная ошибка: {str(e)}"
```

### 4. Контекстные инструменты

```python
@function_tool
async def store_user_preference(
    ctx: RunContextWrapper[MasterContext],
    preference_key: str,
    preference_value: str
) -> str:
    """Сохраняет пользовательские предпочтения."""
    
    # Получаем или создаем словарь предпочтений
    preferences = ctx.context.get("user_preferences", {})
    preferences[preference_key] = preference_value
    
    # Сохраняем обратно в контекст
    ctx.context.set("user_preferences", preferences)
    
    return f"Предпочтение сохранено: {preference_key} = {preference_value}"

@function_tool
async def get_user_preference(
    ctx: RunContextWrapper[MasterContext],
    preference_key: str
) -> str:
    """Получает пользовательские предпочтения."""
    
    preferences = ctx.context.get("user_preferences", {})
    value = preferences.get(preference_key)
    
    if value:
        return f"Предпочтение {preference_key}: {value}"
    else:
        return f"Предпочтение {preference_key} не найдено"
```

---

## Управление состоянием

### 1. Структурирование данных в контексте

```python
# ✅ Хорошая структура контекста
@function_tool
async def initialize_session(
    ctx: RunContextWrapper[MasterContext],
    user_id: str
) -> str:
    """Инициализирует пользовательскую сессию."""
    
    session_data = {
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
        "preferences": {},
        "history": [],
        "current_task": None,
        "metadata": {}
    }
    
    ctx.context.set("session", session_data)
    return f"Сессия инициализирована для пользователя {user_id}"

@function_tool
async def update_task_status(
    ctx: RunContextWrapper[MasterContext],
    task_id: str,
    status: str
) -> str:
    """Обновляет статус задачи."""
    
    session = ctx.context.get("session", {})
    if not session:
        return "Сессия не инициализирована"
    
    # Структурированное обновление
    session["current_task"] = {
        "id": task_id,
        "status": status,
        "updated_at": datetime.now().isoformat()
    }
    
    # Добавляем в историю
    session["history"].append({
        "action": "task_status_update",
        "task_id": task_id,
        "status": status,
        "timestamp": datetime.now().isoformat()
    })
    
    ctx.context.set("session", session)
    return f"Статус задачи {task_id} обновлен на {status}"
```

### 2. Очистка контекста

```python
@function_tool
async def cleanup_old_data(
    ctx: RunContextWrapper[MasterContext],
    max_history_items: int = 100
) -> str:
    """Очищает старые данные из контекста."""
    
    session = ctx.context.get("session", {})
    if not session:
        return "Нет данных для очистки"
    
    # Ограничиваем историю
    if "history" in session and len(session["history"]) > max_history_items:
        session["history"] = session["history"][-max_history_items:]
    
    # Очищаем временные данные
    if "temp_data" in session:
        del session["temp_data"]
    
    ctx.context.set("session", session)
    return f"Контекст очищен. История ограничена {max_history_items} записями"
```

---

## Обработка ошибок

### 1. Graceful degradation

```python
@function_tool
async def get_weather_with_fallback(
    city: str,
    backup_source: bool = True
) -> str:
    """Получает погоду с резервными источниками."""
    
    # Основной источник
    try:
        weather = await get_weather_primary(city)
        return f"Погода в {city}: {weather}"
    except Exception as e:
        print(f"Основной источник недоступен: {e}")
    
    # Резервный источник
    if backup_source:
        try:
            weather = await get_weather_backup(city)
            return f"Погода в {city} (резервный источник): {weather}"
        except Exception as e:
            print(f"Резервный источник недоступен: {e}")
    
    # Fallback
    return f"Не удалось получить погоду для {city}. Попробуйте позже."

async def get_weather_primary(city: str) -> str:
    # Имитация основного API
    raise Exception("API недоступен")

async def get_weather_backup(city: str) -> str:
    # Имитация резервного API
    return "Солнечно, +20°C"
```

### 2. Retry механизмы

```python
import asyncio
from functools import wraps

def retry(max_attempts: int = 3, delay: float = 1.0):
    """Декоратор для повторных попыток."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay * (2 ** attempt))  # Exponential backoff
                    
            raise last_exception
        return wrapper
    return decorator

@function_tool
@retry(max_attempts=3, delay=1.0)
async def reliable_api_call(url: str) -> str:
    """API вызов с повторными попытками."""
    # Логика API вызова
    import random
    if random.random() < 0.7:  # 70% вероятность ошибки для демонстрации
        raise Exception("Временная ошибка API")
    
    return "Данные получены успешно"
```

### 3. Валидация и санитизация

```python
@function_tool
async def process_user_input(
    user_input: str = Field(..., min_length=1, max_length=1000)
) -> str:
    """Безопасно обрабатывает пользовательский ввод."""
    
    # Санитизация
    import html
    import re
    
    # Экранируем HTML
    sanitized = html.escape(user_input.strip())
    
    # Удаляем потенциально опасные символы
    sanitized = re.sub(r'[<>"\']', '', sanitized)
    
    # Проверяем длину после санитизации
    if len(sanitized) == 0:
        return "Ошибка: пустой ввод после санитизации"
    
    if len(sanitized) > 500:
        sanitized = sanitized[:500] + "..."
    
    return f"Обработанный ввод: {sanitized}"
```

---

## Тестирование

### 1. Юнит-тесты для инструментов

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_calculate_roi():
    """Тест расчета ROI."""
    result = await calculate_roi(100000, 150000, 12)
    assert "ROI: 50.0%" in result
    assert "прибыль" in result

@pytest.mark.asyncio
async def test_calculate_roi_loss():
    """Тест расчета ROI с убытком."""
    result = await calculate_roi(100000, 80000, 6)
    assert "ROI: -20.0%" in result
    assert "убыток" in result

@pytest.mark.asyncio
async def test_email_validation():
    """Тест валидации email."""
    valid_data = EmailData(
        email="test@example.com",
        subject="Test Subject",
        body="Test body content"
    )
    assert valid_data.email == "test@example.com"
    
    with pytest.raises(ValueError):
        EmailData(
            email="invalid-email",
            subject="Test",
            body="Test body"
        )
```

### 2. Интеграционные тесты

```python
@pytest.mark.asyncio
async def test_agent_workflow():
    """Тест полного рабочего процесса агента."""
    
    # Создаем тестового агента
    test_agent = Agent(
        name="TestAgent",
        instructions="Отвечай 'Тест пройден' на любое сообщение",
        tools=[]
    )
    
    # Создаем агентство
    test_agency = Agency(test_agent)
    
    # Тестируем ответ
    response = await test_agency.get_response("Тестовое сообщение")
    assert "Тест пройден" in response.final_output

@pytest.mark.asyncio
async def test_multi_agent_communication():
    """Тест коммуникации между агентами."""
    
    sender = Agent(
        name="Sender",
        instructions="Отправь сообщение 'Привет' агенту Receiver"
    )
    
    receiver = Agent(
        name="Receiver", 
        instructions="Отвечай 'Привет получен' на любое сообщение"
    )
    
    agency = Agency(
        sender,
        communication_flows=[sender > receiver]
    )
    
    response = await agency.get_response("Отправь приветствие")
    # Проверяем, что произошла коммуникация
    assert len(response.new_items) > 1  # Должно быть несколько действий
```

### 3. Моки для внешних сервисов

```python
@pytest.mark.asyncio
@patch('aiohttp.ClientSession.get')
async def test_api_call_with_mock(mock_get):
    """Тест API вызова с моком."""
    
    # Настраиваем мок
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value='{"result": "success"}')
    mock_get.return_value.__aenter__.return_value = mock_response
    
    # Тестируем функцию
    result = await fetch_api_data("https://api.example.com/data")
    
    assert "Данные получены успешно" in result
    mock_get.assert_called_once()
```

---

## Производительность

### 1. Асинхронные операции

```python
import asyncio

@function_tool
async def parallel_data_processing(
    ctx: RunContextWrapper[MasterContext],
    data_sources: list[str]
) -> str:
    """Параллельно обрабатывает несколько источников данных."""
    
    async def process_source(source: str) -> dict:
        # Имитация обработки источника
        await asyncio.sleep(1)  # Имитация I/O операции
        return {"source": source, "data": f"processed_{source}"}
    
    # Параллельная обработка
    tasks = [process_source(source) for source in data_sources]
    results = await asyncio.gather(*tasks)
    
    # Сохраняем результаты в контекст
    ctx.context.set("processed_data", results)
    
    return f"Обработано {len(results)} источников параллельно"
```

### 2. Кэширование

```python
from functools import lru_cache
import time

# Простой кэш в памяти
_cache = {}
_cache_ttl = {}

def cached_result(ttl_seconds: int = 300):
    """Декоратор для кэширования результатов."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Создаем ключ кэша
            cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"
            current_time = time.time()
            
            # Проверяем кэш
            if (cache_key in _cache and 
                cache_key in _cache_ttl and 
                current_time - _cache_ttl[cache_key] < ttl_seconds):
                return _cache[cache_key]
            
            # Выполняем функцию и кэшируем результат
            result = await func(*args, **kwargs)
            _cache[cache_key] = result
            _cache_ttl[cache_key] = current_time
            
            return result
        return wrapper
    return decorator

@function_tool
@cached_result(ttl_seconds=600)  # Кэш на 10 минут
async def expensive_calculation(
    data: str,
    complexity: int = 1
) -> str:
    """Дорогостоящие вычисления с кэшированием."""
    
    # Имитация сложных вычислений
    await asyncio.sleep(complexity)
    
    result = f"Результат для {data} (сложность: {complexity})"
    return result
```

### 3. Оптимизация контекста

```python
@function_tool
async def optimize_context_size(
    ctx: RunContextWrapper[MasterContext],
    max_items: int = 1000
) -> str:
    """Оптимизирует размер контекста."""
    
    # Получаем все ключи контекста
    user_context = ctx.context.user_context
    
    # Подсчитываем размер
    total_items = sum(len(str(v)) for v in user_context.values())
    
    if total_items > max_items:
        # Удаляем старые временные данные
        keys_to_remove = [k for k in user_context.keys() if k.startswith("temp_")]
        for key in keys_to_remove:
            del user_context[key]
        
        return f"Контекст оптимизирован. Удалено {len(keys_to_remove)} временных ключей"
    
    return f"Контекст в норме. Размер: {total_items} символов"
```

---

## Безопасность

### 1. Валидация входных данных

```python
import re
from typing import List

ALLOWED_DOMAINS = ["example.com", "trusted-api.com"]
BLOCKED_PATTERNS = [r"<script", r"javascript:", r"data:"]

@function_tool
async def secure_url_fetch(
    url: str = Field(..., description="URL для безопасного запроса")
) -> str:
    """Безопасно получает данные по URL."""
    
    # Валидация URL
    if not url.startswith(("http://", "https://")):
        return "Ошибка: разрешены только HTTP/HTTPS URL"
    
    # Проверка домена
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.netloc not in ALLOWED_DOMAINS:
        return f"Ошибка: домен {parsed.netloc} не разрешен"
    
    # Проверка на вредоносные паттерны
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return f"Ошибка: URL содержит запрещенный паттерн"
    
    # Безопасный запрос
    try:
        # Здесь был бы реальный HTTP запрос
        return f"Данные безопасно получены с {url}"
    except Exception as e:
        return f"Ошибка запроса: {str(e)}"
```

### 2. Ограничение ресурсов

```python
import asyncio
from contextlib import asynccontextmanager

class ResourceLimiter:
    def __init__(self, max_concurrent: int = 5):
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    @asynccontextmanager
    async def acquire(self):
        async with self.semaphore:
            yield

# Глобальный лимитер ресурсов
resource_limiter = ResourceLimiter(max_concurrent=3)

@function_tool
async def limited_resource_operation(
    operation_type: str,
    data: str
) -> str:
    """Операция с ограничением ресурсов."""
    
    async with resource_limiter.acquire():
        # Имитация ресурсоемкой операции
        await asyncio.sleep(2)
        return f"Операция {operation_type} завершена для {data}"
```

### 3. Логирование и аудит

```python
import logging
from datetime import datetime

# Настройка логгера безопасности
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.INFO)

@function_tool
async def secure_data_access(
    ctx: RunContextWrapper[MasterContext],
    data_id: str,
    user_id: str = None
) -> str:
    """Безопасный доступ к данным с логированием."""
    
    # Получаем ID пользователя из контекста если не передан
    if not user_id:
        session = ctx.context.get("session", {})
        user_id = session.get("user_id", "anonymous")
    
    # Логируем попытку доступа
    security_logger.info(
        f"Data access attempt: user={user_id}, data_id={data_id}, "
        f"timestamp={datetime.now().isoformat()}"
    )
    
    # Проверка прав доступа (упрощенная)
    if user_id == "anonymous":
        security_logger.warning(f"Unauthorized access attempt to {data_id}")
        return "Ошибка: требуется авторизация"
    
    # Имитация получения данных
    security_logger.info(f"Data access granted: user={user_id}, data_id={data_id}")
    return f"Данные {data_id} предоставлены пользователю {user_id}"
```

---

## Заключение

Следование этим лучшим практикам поможет вам создавать надежные, масштабируемые и безопасные многоагентные системы на Agency Swarm. Помните:

1. **Начинайте просто** - создавайте минимальные рабочие версии
2. **Тестируйте рано и часто** - каждый компонент должен быть протестирован
3. **Документируйте все** - хорошая документация экономит время
4. **Мониторьте производительность** - следите за метриками
5. **Обеспечивайте безопасность** - валидируйте все входные данные

Эти принципы помогут вам избежать распространенных ошибок и создать качественные решения.
