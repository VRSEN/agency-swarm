# Быстрый справочник Agency Swarm

Краткое руководство по основным возможностям Agency Swarm v1.x для быстрого старта.

## 🚀 Быстрый старт

### Установка
```bash
pip install agency-swarm
```

### Минимальный пример
```python
from agency_swarm import Agency, Agent, function_tool

@function_tool
async def hello_world(name: str) -> str:
    """Приветствует пользователя."""
    return f"Привет, {name}!"

agent = Agent(
    name="Assistant",
    instructions="Ты дружелюбный помощник",
    tools=[hello_world]
)

agency = Agency(agent)

# Использование
response = await agency.get_response("Поздоровайся с Алексеем")
print(response.final_output)
```

---

## 📋 Основные компоненты

### Agent (Агент)
```python
from agency_swarm import Agent

agent = Agent(
    name="AgentName",                    # Имя агента
    instructions="Описание роли...",     # Инструкции
    tools=[tool1, tool2],               # Список инструментов
    output_type=MyModel,                # Структурированный вывод (опционально)
    model="gpt-4o",                     # Модель OpenAI (опционально)
    temperature=0.1                     # Температура (опционально)
)
```

### Agency (Агентство)
```python
from agency_swarm import Agency

agency = Agency(
    main_agent,                         # Главный агент
    communication_flows=[               # Потоки коммуникации
        main_agent > specialist_agent,
        specialist_agent > main_agent
    ],
    shared_instructions="Общие правила", # Общие инструкции
    max_prompt_tokens=25000,            # Лимит токенов
    temperature=0.3                     # Температура по умолчанию
)
```

### function_tool (Инструмент)
```python
from agency_swarm import function_tool, RunContextWrapper, MasterContext
from pydantic import Field

@function_tool
async def my_tool(
    ctx: RunContextWrapper[MasterContext],  # Контекст (опционально)
    param1: str = Field(..., description="Описание параметра"),
    param2: int = Field(default=10, ge=1, le=100)
) -> str:
    """Описание инструмента."""
    
    # Работа с контекстом
    data = ctx.context.get("key", default_value)
    ctx.context.set("key", new_value)
    
    return "Результат работы инструмента"
```

---

## 🔧 Паттерны использования

### 1. Простой агент
```python
simple_agent = Agent(
    name="SimpleBot",
    instructions="Отвечай кратко и по делу",
    tools=[]
)

agency = Agency(simple_agent)
```

### 2. Агент с инструментами
```python
@function_tool
async def calculate(a: float, b: float, operation: str) -> str:
    """Выполняет математические операции."""
    if operation == "add":
        return str(a + b)
    elif operation == "multiply":
        return str(a * b)
    return "Неизвестная операция"

calculator = Agent(
    name="Calculator",
    instructions="Ты калькулятор. Используй инструмент calculate для вычислений.",
    tools=[calculate]
)
```

### 3. Многоагентная система
```python
coordinator = Agent(
    name="Coordinator",
    instructions="Координируй работу специалистов"
)

specialist = Agent(
    name="Specialist", 
    instructions="Выполняй специализированные задачи"
)

agency = Agency(
    coordinator,
    communication_flows=[
        coordinator > specialist,
        specialist > coordinator
    ]
)
```

### 4. Агент со структурированным выводом
```python
from pydantic import BaseModel

class TaskResult(BaseModel):
    status: str
    message: str
    data: dict

structured_agent = Agent(
    name="StructuredAgent",
    instructions="Возвращай результаты в структурированном виде",
    output_type=TaskResult
)
```

---

## 💾 Работа с контекстом

### Сохранение данных
```python
@function_tool
async def save_data(
    ctx: RunContextWrapper[MasterContext],
    key: str,
    value: str
) -> str:
    ctx.context.set(key, value)
    return f"Сохранено: {key} = {value}"
```

### Получение данных
```python
@function_tool
async def get_data(
    ctx: RunContextWrapper[MasterContext],
    key: str
) -> str:
    value = ctx.context.get(key, "Не найдено")
    return f"{key}: {value}"
```

### Работа со сложными данными
```python
@function_tool
async def manage_list(
    ctx: RunContextWrapper[MasterContext],
    action: str,
    item: str = None
) -> str:
    items = ctx.context.get("items", [])
    
    if action == "add" and item:
        items.append(item)
        ctx.context.set("items", items)
        return f"Добавлено: {item}"
    
    elif action == "list":
        return f"Элементы: {', '.join(items)}"
    
    return "Неизвестное действие"
```

---

## 🔄 Методы Agency

### get_response (Обычный ответ)
```python
response = await agency.get_response(
    message="Ваше сообщение",
    recipient_agent="AgentName",  # Опционально
    additional_instructions="Дополнительные инструкции"  # Опционально
)

print(response.final_output)  # Финальный ответ
print(response.new_items)     # Все действия агентов
```

### get_response_stream (Потоковый ответ)
```python
async for chunk in agency.get_response_stream("Создай план проекта"):
    print(chunk, end="", flush=True)
```

---

## 🛠️ Полезные инструменты

### Файловые операции
```python
@function_tool
async def read_file(file_path: str) -> str:
    """Читает содержимое файла."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Ошибка чтения файла: {str(e)}"

@function_tool
async def write_file(file_path: str, content: str) -> str:
    """Записывает содержимое в файл."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Файл {file_path} записан успешно"
    except Exception as e:
        return f"Ошибка записи файла: {str(e)}"
```

### HTTP запросы
```python
import aiohttp

@function_tool
async def fetch_url(url: str) -> str:
    """Получает данные по URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    return f"Данные получены: {len(text)} символов"
                else:
                    return f"HTTP ошибка: {response.status}"
    except Exception as e:
        return f"Ошибка запроса: {str(e)}"
```

### Работа с JSON
```python
import json

@function_tool
async def parse_json(
    ctx: RunContextWrapper[MasterContext],
    json_string: str
) -> str:
    """Парсит JSON и сохраняет в контекст."""
    try:
        data = json.loads(json_string)
        ctx.context.set("parsed_json", data)
        return f"JSON распарсен. Ключей: {len(data) if isinstance(data, dict) else 'N/A'}"
    except json.JSONDecodeError as e:
        return f"Ошибка парсинга JSON: {str(e)}"
```

---

## 🔍 Отладка

### Логирование
```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("my_agency")

@function_tool
async def debug_tool(param: str) -> str:
    logger.debug(f"Вызван debug_tool с параметром: {param}")
    return f"Отладка: {param}"
```

### Диагностика контекста
```python
@function_tool
async def diagnose_context(ctx: RunContextWrapper[MasterContext]) -> str:
    """Показывает состояние контекста."""
    user_context = ctx.context.user_context
    keys = list(user_context.keys())
    size = len(str(user_context))
    
    return f"Контекст: {len(keys)} ключей, {size} символов. Ключи: {keys[:5]}"
```

---

## ⚡ Лучшие практики

### ✅ Делайте
- Используйте четкие имена агентов и инструментов
- Пишите подробные инструкции и описания
- Обрабатывайте ошибки в инструментах
- Тестируйте каждый компонент отдельно
- Используйте структурированные выходы для сложных данных

### ❌ Избегайте
- Слишком общих инструкций агентам
- Инструментов без обработки ошибок
- Прямого изменения user_context
- Слишком сложных инструментов
- Циклических зависимостей в communication_flows

---

## 📚 Примеры команд

```python
# Простой запрос
response = await agency.get_response("Привет!")

# Запрос к конкретному агенту
response = await agency.get_response(
    message="Выполни анализ",
    recipient_agent="Analyst"
)

# С дополнительными инструкциями
response = await agency.get_response(
    message="Создай отчет",
    additional_instructions="Сделай его кратким"
)

# Потоковый ответ
async for chunk in agency.get_response_stream("Расскажи историю"):
    print(chunk, end="")
```

---

## 🔗 Полезные ссылки

- [Полное руководство](comprehensive-guide-ru.md)
- [Практические примеры](practical-examples-ru.md)
- [Лучшие практики](best-practices-ru.md)
- [GitHub репозиторий](https://github.com/VRSEN/agency-swarm)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)

---

*Этот справочник покрывает основные возможности Agency Swarm. Для более подробной информации обратитесь к полному руководству.*
