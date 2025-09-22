# Руководство по миграции Agency Swarm

Полное руководство по миграции с v0.x на v1.x и обновлению существующих проектов.

## 📋 Содержание

1. [Обзор изменений](#обзор-изменений)
2. [Подготовка к миграции](#подготовка-к-миграции)
3. [Пошаговая миграция](#пошаговая-миграция)
4. [Изменения в API](#изменения-в-api)
5. [Новые возможности](#новые-возможности)
6. [Устранение проблем](#устранение-проблем)

---

## 🔄 Обзор изменений

### Основные изменения в v1.x

| Компонент | v0.x | v1.x | Статус |
|-----------|------|------|--------|
| **Базовый класс** | Собственная реализация | OpenAI Agents SDK | ✅ Обновлено |
| **Async/Await** | Частичная поддержка | Полная поддержка | ✅ Улучшено |
| **Инструменты** | `BaseTool` класс | `@function_tool` декоратор | ✅ Упрощено |
| **Контекст** | Простой словарь | `MasterContext` класс | ✅ Улучшено |
| **Персистентность** | Только thread ID | Полная история | ✅ Расширено |
| **Валидация** | Базовая | Pydantic модели | ✅ Улучшено |
| **Потоки** | Нет | Streaming API | 🆕 Новое |

### Преимущества v1.x

- **Лучшая производительность** благодаря async/await
- **Упрощенное создание инструментов** с декораторами
- **Улучшенное управление состоянием** через MasterContext
- **Полная персистентность** разговоров
- **Структурированные выходы** с Pydantic
- **Потоковые ответы** для лучшего UX

---

## 🛠️ Подготовка к миграции

### 1. Аудит существующего кода

Создайте список всех компонентов для миграции:

```bash
# Найдите все файлы с Agency Swarm
find . -name "*.py" -exec grep -l "agency_swarm" {} \;

# Найдите использование старых классов
grep -r "BaseTool" --include="*.py" .
grep -r "Agency(" --include="*.py" .
grep -r "Agent(" --include="*.py" .
```

### 2. Создайте резервную копию

```bash
# Создайте ветку для миграции
git checkout -b migration-to-v1

# Или скопируйте проект
cp -r my_project my_project_backup
```

### 3. Обновите зависимости

```bash
# Обновите Agency Swarm
pip install --upgrade agency-swarm

# Проверьте версию
python -c "import agency_swarm; print(agency_swarm.__version__)"
```

---

## 🔧 Пошаговая миграция

### Шаг 1: Миграция инструментов

**v0.x (старый способ):**
```python
from agency_swarm.tools import BaseTool
from pydantic import Field

class CalculatorTool(BaseTool):
    """Инструмент для вычислений."""
    
    a: float = Field(..., description="Первое число")
    b: float = Field(..., description="Второе число")
    operation: str = Field(..., description="Операция: add, subtract, multiply, divide")
    
    def run(self):
        if self.operation == "add":
            return self.a + self.b
        elif self.operation == "subtract":
            return self.a - self.b
        elif self.operation == "multiply":
            return self.a * self.b
        elif self.operation == "divide":
            return self.a / self.b if self.b != 0 else "Деление на ноль"
        else:
            return "Неизвестная операция"
```

**v1.x (новый способ):**
```python
from agency_swarm import function_tool
from pydantic import Field

@function_tool
async def calculator_tool(
    a: float = Field(..., description="Первое число"),
    b: float = Field(..., description="Второе число"),
    operation: str = Field(..., description="Операция: add, subtract, multiply, divide")
) -> str:
    """Инструмент для вычислений."""
    
    if operation == "add":
        return str(a + b)
    elif operation == "subtract":
        return str(a - b)
    elif operation == "multiply":
        return str(a * b)
    elif operation == "divide":
        return str(a / b) if b != 0 else "Деление на ноль"
    else:
        return "Неизвестная операция"
```

### Шаг 2: Миграция агентов

**v0.x:**
```python
from agency_swarm import Agent

agent = Agent(
    name="Calculator",
    description="Агент для математических вычислений",
    instructions="Выполняй математические операции",
    tools=[CalculatorTool],
    model="gpt-4"
)
```

**v1.x:**
```python
from agency_swarm import Agent

agent = Agent(
    name="Calculator",
    instructions="Ты математический калькулятор. Используй calculator_tool для вычислений.",
    tools=[calculator_tool],
    model="gpt-4o"  # Обновленная модель
)
```

### Шаг 3: Миграция агентства

**v0.x:**
```python
from agency_swarm import Agency

agency = Agency([
    agent1,
    [agent1, agent2],  # Коммуникационная матрица
    [agent2, agent1]
])
```

**v1.x:**
```python
from agency_swarm import Agency

agency = Agency(
    agent1,  # Главный агент
    communication_flows=[
        agent1 > agent2,
        agent2 > agent1
    ]
)
```

### Шаг 4: Миграция контекста

**v0.x:**
```python
# Контекст был недоступен в инструментах
class MyTool(BaseTool):
    def run(self):
        # Нет доступа к общему состоянию
        return "result"
```

**v1.x:**
```python
from agency_swarm import function_tool, RunContextWrapper, MasterContext

@function_tool
async def my_tool(
    ctx: RunContextWrapper[MasterContext],
    param: str
) -> str:
    # Доступ к общему состоянию
    data = ctx.context.get("shared_data", {})
    data["last_param"] = param
    ctx.context.set("shared_data", data)
    
    return f"Обработано: {param}"
```

### Шаг 5: Миграция вызовов

**v0.x:**
```python
# Синхронные вызовы
response = agency.get_completion("Вычисли 2 + 2")
print(response)
```

**v1.x:**
```python
import asyncio

# Асинхронные вызовы
async def main():
    response = await agency.get_response("Вычисли 2 + 2")
    print(response.final_output)

asyncio.run(main())
```

---

## 📝 Изменения в API

### Методы Agency

| v0.x | v1.x | Описание |
|------|------|----------|
| `get_completion()` | `get_response()` | Основной метод получения ответа |
| `get_completion_stream()` | `get_response_stream()` | Потоковый ответ |
| - | `get_response(..., recipient_agent="Name")` | Отправка к конкретному агенту |

### Структура ответа

**v0.x:**
```python
response = agency.get_completion("Привет")
# response - строка
print(response)
```

**v1.x:**
```python
response = await agency.get_response("Привет")
# response - объект с атрибутами
print(response.final_output)  # Финальный ответ
print(response.new_items)     # Все действия
```

### Персистентность

**v0.x:**
```python
# Сохранялся только thread_id
agency.save_state("thread_123")
```

**v1.x:**
```python
# Полная персистентность через колбэки
def save_conversation(conversation_data):
    with open("conversation.json", "w") as f:
        json.dump(conversation_data, f)

def load_conversation():
    try:
        with open("conversation.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None

agency = Agency(
    agent,
    persistence_hooks={
        "save": save_conversation,
        "load": load_conversation
    }
)
```

---

## 🆕 Новые возможности

### 1. Структурированные выходы

```python
from pydantic import BaseModel

class TaskResult(BaseModel):
    status: str
    message: str
    data: dict

agent = Agent(
    name="StructuredAgent",
    instructions="Возвращай результаты в структурированном виде",
    output_type=TaskResult
)

# Ответ будет автоматически валидирован
response = await agency.get_response("Выполни задачу")
result = response.final_output  # Объект TaskResult
```

### 2. Потоковые ответы

```python
# Получение ответа по частям
async for chunk in agency.get_response_stream("Расскажи длинную историю"):
    print(chunk, end="", flush=True)
```

### 3. Улучшенная валидация

```python
@function_tool
async def validated_tool(
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$'),
    age: int = Field(..., ge=0, le=150),
    score: float = Field(..., ge=0.0, le=100.0)
) -> str:
    """Инструмент с валидацией входных данных."""
    return f"Email: {email}, Age: {age}, Score: {score}"
```

### 4. Контекстные инструменты

```python
@function_tool
async def context_aware_tool(
    ctx: RunContextWrapper[MasterContext],
    action: str
) -> str:
    """Инструмент с доступом к контексту."""
    
    # Получение данных
    user_data = ctx.context.get("user_data", {})
    
    # Обновление данных
    user_data["last_action"] = action
    ctx.context.set("user_data", user_data)
    
    return f"Выполнено: {action}"
```

---

## 🔧 Устранение проблем

### Проблема 1: Инструменты не работают

**Симптом:** Агент не использует инструменты или выдает ошибки.

**Решение:**
```python
# Проверьте, что инструмент async
@function_tool
async def my_tool(param: str) -> str:  # Обязательно async!
    return f"Result: {param}"

# Проверьте типы возвращаемых значений
@function_tool
async def my_tool(param: str) -> str:  # Возвращайте строку
    return str(result)  # Приведите к строке
```

### Проблема 2: Ошибки контекста

**Симптом:** `AttributeError` при работе с контекстом.

**Решение:**
```python
# Используйте правильную сигнатуру
@function_tool
async def context_tool(
    ctx: RunContextWrapper[MasterContext],  # Правильный тип
    param: str
) -> str:
    # Используйте методы get/set
    value = ctx.context.get("key", "default")
    ctx.context.set("key", "new_value")
    return "OK"
```

### Проблема 3: Async/Await ошибки

**Симптом:** `RuntimeError: This event loop is already running`

**Решение:**
```python
# В Jupyter/IPython используйте nest_asyncio
import nest_asyncio
nest_asyncio.apply()

# Или используйте await напрямую в Jupyter
response = await agency.get_response("Привет")

# В обычном Python используйте asyncio.run()
import asyncio

async def main():
    response = await agency.get_response("Привет")
    print(response.final_output)

if __name__ == "__main__":
    asyncio.run(main())
```

### Проблема 4: Персистентность не работает

**Симптом:** Разговоры не сохраняются между сессиями.

**Решение:**
```python
import json
from pathlib import Path

def save_conversation(data):
    """Сохраняет разговор в файл."""
    Path("conversations").mkdir(exist_ok=True)
    with open("conversations/latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_conversation():
    """Загружает разговор из файла."""
    try:
        with open("conversations/latest.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None

agency = Agency(
    agent,
    persistence_hooks={
        "save": save_conversation,
        "load": load_conversation
    }
)
```

---

## ✅ Чек-лист миграции

### Перед миграцией
- [ ] Создана резервная копия проекта
- [ ] Проведен аудит существующего кода
- [ ] Обновлена версия Agency Swarm
- [ ] Изучены новые возможности v1.x

### Во время миграции
- [ ] Мигрированы все инструменты с BaseTool на @function_tool
- [ ] Обновлены агенты (убрано description, обновлены instructions)
- [ ] Изменена структура Agency (communication_flows)
- [ ] Добавлены async/await во все вызовы
- [ ] Обновлена работа с контекстом

### После миграции
- [ ] Все тесты проходят
- [ ] Функциональность работает как ожидается
- [ ] Добавлены новые возможности (структурированные выходы, потоки)
- [ ] Настроена персистентность
- [ ] Обновлена документация

---

## 📚 Дополнительные ресурсы

- [Полное руководство](comprehensive-guide-ru.md)
- [Практические примеры](practical-examples-ru.md)
- [Лучшие практики](best-practices-ru.md)
- [Быстрый справочник](quick-reference-ru.md)
- [Официальная документация миграции](../docs/migration/guide.mdx)

---

*Миграция может показаться сложной, но новые возможности v1.x стоят затраченных усилий. При возникновении проблем обращайтесь к документации или сообществу разработчиков.*
