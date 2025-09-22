# Полное руководство по Agency Swarm v1.x

## Содержание

1. [Введение](#введение)
2. [Установка и настройка](#установка-и-настройка)
3. [Основные концепции](#основные-концепции)
4. [Создание агентов](#создание-агентов)
5. [Система инструментов](#система-инструментов)
6. [Многоагентные системы](#многоагентные-системы)
7. [Управление состоянием](#управление-состоянием)
8. [Персистентность данных](#персистентность-данных)
9. [Продвинутые возможности](#продвинутые-возможности)
10. [Лучшие практики](#лучшие-практики)
11. [Примеры из реального мира](#примеры-из-реального-мира)
12. [Устранение неполадок](#устранение-неполадок)

---

## Введение

Agency Swarm v1.x — это мощный фреймворк для создания многоагентных систем на основе OpenAI Agents SDK. Он позволяет создавать сложные системы ИИ-агентов, которые могут взаимодействовать друг с другом, обмениваться данными и выполнять координированные задачи.

### Ключевые особенности v1.x

- **Современная архитектура**: Построен на OpenAI Agents SDK v1.x
- **Асинхронное выполнение**: Нативная поддержка async/await
- **Прямое управление**: Полный контроль над потоками и выполнением
- **Структурированные выходы**: Поддержка Pydantic моделей
- **Улучшенная система инструментов**: Декоратор `@function_tool`
- **Гибкая коммуникация**: Определяемые потоки коммуникации
- **Управление состоянием**: Общий контекст между агентами

---

## Установка и настройка

### Установка

```bash
pip install agency-swarm
```

### Настройка окружения

Создайте файл `.env` в корне проекта:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

### Базовая настройка

```python
from dotenv import load_dotenv
load_dotenv()

from agency_swarm import Agency, Agent, function_tool
```

---

## Основные концепции

### Архитектура Agency Swarm

Agency Swarm состоит из нескольких ключевых компонентов:

1. **Agency** — оркестратор, управляющий агентами и их взаимодействием
2. **Agent** — отдельный ИИ-агент с определенными возможностями
3. **Tools** — инструменты, которые агенты могут использовать
4. **ThreadManager** — управление историей сообщений
5. **MasterContext** — общий контекст между агентами

### Паттерн "Оркестратор-Исполнители"

Agency Swarm использует проверенный паттерн, где:
- **Оркестратор** — главный агент, координирующий работу
- **Исполнители** — специализированные агенты для конкретных задач

```python
# Оркестратор
ceo = Agent(
    name="CEO",
    instructions="Координируй работу команды и принимай решения"
)

# Исполнители
developer = Agent(
    name="Developer", 
    instructions="Пиши и тестируй код"
)

analyst = Agent(
    name="Analyst",
    instructions="Анализируй данные и создавай отчеты"
)

# Агентство с потоками коммуникации
agency = Agency(
    ceo,  # Точка входа
    communication_flows=[
        ceo > developer,
        ceo > analyst
    ]
)
```

---

## Создание агентов

### Базовый агент

```python
from agency_swarm import Agent, ModelSettings

agent = Agent(
    name="MyAgent",
    description="Описание агента для других агентов",
    instructions="Подробные инструкции для агента",
    model_settings=ModelSettings(
        model="gpt-4o",
        temperature=0.7,
        max_completion_tokens=2000
    )
)
```

### Агент с инструментами

```python
@function_tool
def calculate_sum(a: int, b: int) -> str:
    """Складывает два числа."""
    return str(a + b)

calculator_agent = Agent(
    name="Calculator",
    instructions="Ты умеешь выполнять математические вычисления",
    tools=[calculate_sum]
)
```

### Агент с файлами и схемами

```python
agent = Agent(
    name="FileAgent",
    instructions="./instructions.md",  # Инструкции из файла
    files_folder="./files",            # Файлы для загрузки в OpenAI
    schemas_folder="./schemas",        # OpenAPI схемы → инструменты
    tools_folder="./tools"             # Папка с инструментами
)
```

### Структурированные выходы

```python
from pydantic import BaseModel, Field

class AnalysisResult(BaseModel):
    status: str = Field(..., description="Статус анализа")
    findings: list[str] = Field(..., description="Основные находки")
    recommendation: str = Field(..., description="Рекомендация")

analyst = Agent(
    name="Analyst",
    instructions="Анализируй данные и возвращай структурированный результат",
    output_type=AnalysisResult  # Агент будет возвращать типизированный объект
)
```

---

## Система инструментов

### Декоратор @function_tool (рекомендуется)

```python
from agency_swarm import function_tool, RunContextWrapper, MasterContext

@function_tool
def simple_tool(text: str) -> str:
    """Простой инструмент без контекста."""
    return f"Обработано: {text}"

@function_tool
async def advanced_tool(
    ctx: RunContextWrapper[MasterContext], 
    data: str
) -> str:
    """Продвинутый инструмент с доступом к контексту."""
    # Доступ к общему контексту
    shared_data = ctx.context.get("shared_key", "default")
    
    # Сохранение данных в контекст
    ctx.context.set("last_processed", data)
    
    return f"Результат: {data} + {shared_data}"
```

### BaseTool (альтернативный подход)

```python
from agency_swarm.tools import BaseTool
from pydantic import Field

class CustomTool(BaseTool):
    """Описание инструмента для агента."""
    
    input_data: str = Field(..., description="Входные данные")
    
    def run(self) -> str:
        # Доступ к контексту
        shared_data = self.context.get("key", "default")
        
        # Ваша логика
        result = self.process_data(self.input_data)
        
        return str(result)
    
    def process_data(self, data: str) -> str:
        return f"Обработано: {data}"
```

### Валидация инструментов

```python
from pydantic import BaseModel, Field, field_validator

class CalculatorArgs(BaseModel):
    a: int = Field(..., ge=0, description="Первое число (>= 0)")
    b: int = Field(..., ge=0, description="Второе число (>= 0)")
    
    @field_validator("a", "b")
    @classmethod
    def validate_range(cls, v: int) -> int:
        if v > 1000:
            raise ValueError("Число должно быть <= 1000")
        return v

@function_tool
def safe_calculator(args: CalculatorArgs) -> str:
    """Безопасный калькулятор с валидацией."""
    return str(args.a + args.b)
```

---

## Многоагентные системы

### Создание агентства

```python
from agency_swarm import Agency

# Определение агентов
manager = Agent(name="Manager", instructions="Управляй проектом")
developer = Agent(name="Developer", instructions="Разрабатывай код") 
tester = Agent(name="Tester", instructions="Тестируй код")

# Создание агентства
agency = Agency(
    manager,  # Точка входа (обязательный позиционный аргумент)
    communication_flows=[
        manager > developer,  # Manager может общаться с Developer
        manager > tester,     # Manager может общаться с Tester
        developer > tester    # Developer может общаться с Tester
    ],
    shared_instructions="Следуй лучшим практикам разработки"
)
```

### Получение ответа от агентства

```python
import asyncio

async def main():
    # Простой запрос
    response = await agency.get_response("Создай простое веб-приложение")
    print(response.final_output)
    
    # Запрос к конкретному агенту
    response = await agency.get_response(
        message="Протестируй этот код",
        recipient_agent="Tester"
    )
    
    # Потоковый ответ
    async for chunk in agency.get_response_stream("Создай план проекта"):
        print(chunk)

asyncio.run(main())
```

### Коммуникация между агентами

Агенты автоматически получают инструмент `SendMessage` для общения:

```python
# В инструкциях агента-оркестратора:
manager_instructions = """
Ты менеджер проекта. Когда получаешь задачу:
1. Проанализируй требования
2. Делегируй разработку Developer через SendMessage
3. Попроси Tester протестировать через SendMessage
4. Собери результаты и дай финальный ответ
"""
```

Агенты могут использовать SendMessage так:

```python
# Это происходит автоматически внутри агента
# Агент получает инструмент SendMessage и может писать:
# "Отправлю задачу разработчику: SendMessage(recipient='Developer', message='Создай API для пользователей')"
```

---

## Управление состоянием

### MasterContext — общий контекст

```python
from agency_swarm import MasterContext, RunContextWrapper, function_tool

@function_tool
async def store_data(
    ctx: RunContextWrapper[MasterContext],
    key: str, 
    value: str
) -> str:
    """Сохраняет данные в общий контекст."""
    ctx.context.set(key, value)
    return f"Сохранено: {key} = {value}"

@function_tool  
async def get_data(
    ctx: RunContextWrapper[MasterContext],
    key: str
) -> str:
    """Получает данные из общего контекста."""
    value = ctx.context.get(key, "Не найдено")
    return f"Значение {key}: {value}"
```

### Пользовательский контекст

```python
# При создании агентства
agency = Agency(
    agent,
    user_context={
        "session_id": "user123",
        "preferences": {"language": "ru"},
        "project_data": {}
    }
)

# В инструментах
@function_tool
async def use_user_context(ctx: RunContextWrapper[MasterContext]) -> str:
    session_id = ctx.context.get("session_id")
    preferences = ctx.context.get("preferences", {})
    return f"Сессия: {session_id}, Язык: {preferences.get('language')}"
```

---

## Персистентность данных

### Настройка персистентности

```python
import json
from typing import Any, List, Dict

def load_threads() -> List[Dict[str, Any]]:
    """Загружает историю сообщений из файла/БД."""
    try:
        with open("thread_data.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_threads(messages: List[Dict[str, Any]]) -> None:
    """Сохраняет историю сообщений в файл/БД."""
    with open("thread_data.json", "w") as f:
        json.dump(messages, f, indent=2)

# Агентство с персистентностью
agency = Agency(
    agent,
    load_threads_callback=load_threads,
    save_threads_callback=save_threads
)
```

### Формат данных персистентности

В v1.x сохраняется полная история сообщений:

```python
# Пример структуры сообщения
message_example = {
    "role": "user",
    "content": "Привет!",
    "agent": "MyAgent",           # Получатель
    "callerAgent": None,          # Отправитель (None = пользователь)
    "timestamp": 1703123456789,   # Временная метка
    "parent_run_id": "run_123"    # ID выполнения
}
```

---

## Продвинутые возможности

### Валидация входов и выходов

```python
from agency_swarm import input_guardrail, output_guardrail, GuardrailFunctionOutput

@input_guardrail
async def validate_input(ctx, agent, user_input):
    """Валидация входящих сообщений."""
    if "запрещенное_слово" in user_input.lower():
        return GuardrailFunctionOutput(
            output_info="Сообщение содержит запрещенный контент",
            tripwire_triggered=True
        )
    return GuardrailFunctionOutput(output_info="Вход валиден")

@output_guardrail  
async def validate_output(ctx, agent, agent_response):
    """Валидация ответов агента."""
    if len(agent_response) < 10:
        return GuardrailFunctionOutput(
            output_info="Ответ слишком короткий",
            tripwire_triggered=True
        )
    return GuardrailFunctionOutput(output_info="Ответ валиден")

agent = Agent(
    name="ValidatedAgent",
    instructions="Отвечай подробно и корректно",
    input_guardrails=[validate_input],
    output_guardrails=[validate_output]
)
```

### Интеграция с FastAPI

```python
from fastapi import FastAPI
from agency_swarm import run_fastapi

app = FastAPI()

# Автоматическое создание API эндпоинтов
run_fastapi(
    agency=agency,
    app=app,
    host="0.0.0.0",
    port=8000
)

# Теперь доступны эндпоинты:
# POST /chat - для общения с агентством
# GET /agents - список агентов
# WebSocket /ws - для потокового общения
```

### MCP (Model Context Protocol) серверы

```python
from agency_swarm.tools.mcp_manager import MCPServerStdio

# Подключение файловой системы через MCP
filesystem_server = MCPServerStdio(
    name="FileSystem",
    params={
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    }
)

agent = Agent(
    name="FileAgent",
    instructions="Работай с файлами через MCP",
    mcp_servers=[filesystem_server]
)
```

---

## Лучшие практики

### 1. Структура проекта

```
my_agency/
├── .env                    # Переменные окружения
├── main.py                # Точка входа
├── agents/                # Агенты
│   ├── __init__.py
│   ├── manager.py
│   ├── developer.py
│   └── tester.py
├── tools/                 # Общие инструменты
│   ├── __init__.py
│   ├── database.py
│   └── api_client.py
└── config/               # Конфигурация
    ├── settings.py
    └── prompts.py
```

### 2. Дизайн агентов

```python
# ✅ Хорошо: Четкая специализация
class DataAnalyst(Agent):
    def __init__(self):
        super().__init__(
            name="DataAnalyst",
            instructions="""
            Ты специалист по анализу данных. Твои задачи:
            1. Анализировать предоставленные данные
            2. Создавать визуализации
            3. Формулировать выводы и рекомендации
            
            Всегда используй статистические методы для обоснования выводов.
            """,
            tools=[analyze_data, create_chart, statistical_test]
        )

# ❌ Плохо: Слишком общие инструкции
class GeneralAgent(Agent):
    def __init__(self):
        super().__init__(
            name="GeneralAgent", 
            instructions="Делай всё что попросят"
        )
```

### 3. Обработка ошибок

```python
@function_tool
async def safe_api_call(url: str) -> str:
    """Безопасный вызов API с обработкой ошибок."""
    try:
        # Ваш код API вызова
        response = await make_api_call(url)
        return f"Успех: {response}"
    except Exception as e:
        return f"Ошибка: {str(e)}"

# В агенте
agent = Agent(
    name="APIAgent",
    instructions="""
    При работе с API:
    1. Всегда проверяй результат инструмента
    2. Если получил ошибку, объясни пользователю что произошло
    3. Предложи альтернативные решения
    """
)
```

### 4. Тестирование

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_agent_response():
    """Тест ответа агента."""
    agent = Agent(
        name="TestAgent",
        instructions="Отвечай 'Привет' на любое сообщение"
    )
    
    agency = Agency(agent)
    response = await agency.get_response("Тест")
    
    assert "Привет" in response.final_output

@pytest.mark.asyncio  
async def test_tool_functionality():
    """Тест функциональности инструмента."""
    result = await calculate_sum(5, 3)
    assert result == "8"
```

---

## Примеры из реального мира

### Пример 1: Система анализа документов

```python
from agency_swarm import Agency, Agent, function_tool
import PyPDF2
import docx

@function_tool
async def extract_text_from_pdf(file_path: str) -> str:
    """Извлекает текст из PDF файла."""
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
    return text

@function_tool  
async def extract_text_from_docx(file_path: str) -> str:
    """Извлекает текст из DOCX файла."""
    doc = docx.Document(file_path)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

@function_tool
async def analyze_sentiment(text: str) -> str:
    """Анализирует тональность текста."""
    # Здесь может быть интеграция с ML моделью
    return "Положительная тональность обнаружена"

# Агенты
document_processor = Agent(
    name="DocumentProcessor",
    instructions="Извлекай текст из документов различных форматов",
    tools=[extract_text_from_pdf, extract_text_from_docx]
)

sentiment_analyzer = Agent(
    name="SentimentAnalyzer", 
    instructions="Анализируй тональность и эмоциональную окраску текста",
    tools=[analyze_sentiment]
)

coordinator = Agent(
    name="Coordinator",
    instructions="""
    Координируй анализ документов:
    1. Попроси DocumentProcessor извлечь текст
    2. Передай текст SentimentAnalyzer для анализа
    3. Собери результаты и создай итоговый отчет
    """
)

# Агентство
document_analysis_agency = Agency(
    coordinator,
    communication_flows=[
        coordinator > document_processor,
        coordinator > sentiment_analyzer
    ]
)
```

### Пример 2: E-commerce помощник

```python
@function_tool
async def search_products(query: str, category: str = None) -> str:
    """Ищет товары в каталоге."""
    # Интеграция с API каталога
    return f"Найдено 5 товаров по запросу '{query}'"

@function_tool
async def check_inventory(product_id: str) -> str:
    """Проверяет наличие товара на складе."""
    # Интеграция с системой складского учета
    return f"Товар {product_id}: в наличии 15 штук"

@function_tool
async def calculate_shipping(address: str, weight: float) -> str:
    """Рассчитывает стоимость доставки."""
    # Интеграция с службой доставки
    return f"Стоимость доставки в {address}: 500 руб"

# Специализированные агенты
product_specialist = Agent(
    name="ProductSpecialist",
    instructions="Помогай клиентам найти нужные товары",
    tools=[search_products, check_inventory]
)

logistics_specialist = Agent(
    name="LogisticsSpecialist", 
    instructions="Рассчитывай доставку и сроки",
    tools=[calculate_shipping]
)

customer_service = Agent(
    name="CustomerService",
    instructions="""
    Ты главный консультант интернет-магазина:
    1. Выясни потребности клиента
    2. Попроси ProductSpecialist найти подходящие товары
    3. Попроси LogisticsSpecialist рассчитать доставку
    4. Предложи клиенту лучшие варианты
    """
)

ecommerce_agency = Agency(
    customer_service,
    communication_flows=[
        customer_service > product_specialist,
        customer_service > logistics_specialist
    ]
)
```

---

## Устранение неполадок

### Частые проблемы и решения

#### 1. Агент не использует инструменты

**Проблема**: Агент игнорирует доступные инструменты.

**Решение**:
```python
# ✅ Четко укажи когда использовать инструмент
agent = Agent(
    name="Calculator",
    instructions="""
    Ты калькулятор. ВСЕГДА используй инструмент calculate_sum 
    для сложения чисел. Никогда не считай в уме.
    
    Пример: Если пользователь спрашивает "сколько будет 2+3?",
    используй calculate_sum(2, 3).
    """,
    tools=[calculate_sum]
)
```

#### 2. Агенты не общаются между собой

**Проблема**: Агенты не используют SendMessage.

**Решение**:
```python
# ✅ Явно опиши процесс коммуникации
manager_instructions = """
Ты менеджер команды. Когда получаешь задачу:

1. Проанализируй что нужно сделать
2. ОБЯЗАТЕЛЬНО используй SendMessage для делегирования:
   - Отправь задачу разработчику: SendMessage(recipient="Developer", message="...")
   - Получи результат от разработчика
3. Собери финальный ответ

ВАЖНО: Всегда используй SendMessage для общения с другими агентами!
"""
```

#### 3. Контекст не сохраняется

**Проблема**: Данные теряются между вызовами.

**Решение**:
```python
# ✅ Правильная настройка персистентности
def load_threads():
    try:
        with open("threads.json", "r") as f:
            return json.load(f)
    except:
        return []

def save_threads(messages):
    with open("threads.json", "w") as f:
        json.dump(messages, f)

agency = Agency(
    agent,
    load_threads_callback=load_threads,
    save_threads_callback=save_threads
)
```

#### 4. Ошибки валидации инструментов

**Проблема**: Pydantic валидация блокирует выполнение.

**Решение**:
```python
# ✅ Добавь подробные описания и примеры
class CalculatorArgs(BaseModel):
    a: int = Field(
        ..., 
        ge=0, 
        description="Первое число (должно быть >= 0). Пример: 5"
    )
    b: int = Field(
        ..., 
        ge=0,
        description="Второе число (должно быть >= 0). Пример: 3"  
    )

@function_tool
def calculate(args: CalculatorArgs) -> str:
    """
    Складывает два положительных числа.
    
    Примеры использования:
    - calculate({"a": 5, "b": 3}) -> "8"
    - calculate({"a": 10, "b": 20}) -> "30"
    """
    return str(args.a + args.b)
```

### Отладка

#### Включение логирования

```python
import logging

# Подробное логирование для отладки
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("agency_swarm").setLevel(logging.DEBUG)
```

#### Проверка истории сообщений

```python
# После выполнения запроса
response = await agency.get_response("Тест")

# Проверь историю сообщений
thread_manager = agency.thread_manager
messages = thread_manager.get_all_messages()

for msg in messages:
    print(f"От: {msg.get('callerAgent', 'User')} -> {msg.get('agent')}")
    print(f"Сообщение: {msg.get('content')}")
    print("---")
```

---

## 8. Реальные примеры

### Простой чат-бот с памятью
```python
import asyncio
from agency_swarm import Agency, Agent, function_tool, RunContextWrapper, MasterContext

@function_tool
async def remember_user_info(
    ctx: RunContextWrapper[MasterContext],
    key: str,
    value: str
) -> str:
    """Запоминает информацию о пользователе."""
    user_data = ctx.context.get("user_data", {})
    user_data[key] = value
    ctx.context.set("user_data", user_data)
    return f"Запомнил: {key} = {value}"

@function_tool
async def recall_user_info(
    ctx: RunContextWrapper[MasterContext],
    key: str = None
) -> str:
    """Вспоминает информацию о пользователе."""
    user_data = ctx.context.get("user_data", {})

    if key:
        value = user_data.get(key)
        return f"{key}: {value}" if value else f"Не помню {key}"
    else:
        if user_data:
            info = ", ".join([f"{k}: {v}" for k, v in user_data.items()])
            return f"Что я знаю о вас: {info}"
        return "Я пока ничего о вас не знаю"

chatbot = Agent(
    name="PersonalChatbot",
    instructions="""
    Ты персональный чат-бот с памятью. Твои возможности:

    1. Запоминай информацию о пользователе (имя, предпочтения, интересы)
    2. Используй сохраненную информацию в разговоре
    3. Будь дружелюбным и персонализированным

    Когда пользователь сообщает о себе что-то важное, используй remember_user_info.
    Когда нужно вспомнить информацию, используй recall_user_info.
    """,
    tools=[remember_user_info, recall_user_info]
)

chatbot_agency = Agency(chatbot)
```

### Система анализа данных
```python
from pydantic import BaseModel
from typing import Dict, List

class AnalysisResult(BaseModel):
    summary: str
    key_metrics: Dict[str, float]
    recommendations: List[str]

@function_tool
async def analyze_sales_data(
    ctx: RunContextWrapper[MasterContext],
    data_source: str
) -> str:
    """Анализирует данные продаж."""

    # Имитация анализа данных
    import random

    metrics = {
        "total_sales": random.randint(100000, 500000),
        "growth_rate": random.uniform(-10, 25),
        "avg_order_value": random.randint(1000, 5000)
    }

    recommendations = [
        "Увеличить маркетинговые расходы на 15%",
        "Оптимизировать конверсию на сайте",
        "Расширить ассортимент популярных товаров"
    ]

    result = AnalysisResult(
        summary=f"Анализ данных из {data_source} завершен",
        key_metrics=metrics,
        recommendations=recommendations
    )

    ctx.context.set("last_analysis", result.dict())
    return f"Анализ завершен. Общие продажи: {metrics['total_sales']} руб."

analyst = Agent(
    name="DataAnalyst",
    instructions="Анализируй данные и предоставляй инсайты",
    tools=[analyze_sales_data],
    output_type=AnalysisResult
)

analytics_agency = Agency(analyst)
```

---

## 9. Устранение неполадок

### Частые ошибки и их решения

#### 1. Ошибки инициализации агентов
```python
# ❌ Неправильно
agent = Agent(
    name="",  # Пустое имя
    instructions=None,  # Отсутствуют инструкции
    tools=[]
)

# ✅ Правильно
agent = Agent(
    name="MyAgent",  # Четкое имя
    instructions="Ты помощник по...",  # Ясные инструкции
    tools=[my_tool]  # Список инструментов
)
```

#### 2. Проблемы с инструментами
```python
# ❌ Неправильно - отсутствует async
@function_tool
def broken_tool(param: str) -> str:  # Нет async!
    return "result"

# ✅ Правильно
@function_tool
async def working_tool(param: str) -> str:
    return "result"
```

#### 3. Проблемы с контекстом
```python
# ❌ Неправильно - прямое изменение
@function_tool
async def bad_context_usage(ctx: RunContextWrapper[MasterContext]) -> str:
    ctx.context.user_context["key"] = "value"  # Прямое изменение
    return "done"

# ✅ Правильно - через методы
@function_tool
async def good_context_usage(ctx: RunContextWrapper[MasterContext]) -> str:
    ctx.context.set("key", "value")  # Через метод set
    return "done"
```

### Отладка и диагностика

#### Включение подробного логирования
```python
import logging

# Настройка логирования для Agency Swarm
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("agency_swarm")
logger.setLevel(logging.DEBUG)

# Логирование в инструментах
@function_tool
async def debug_tool(param: str) -> str:
    logger.debug(f"debug_tool вызван с параметром: {param}")

    try:
        result = some_operation(param)
        logger.info(f"Операция успешна: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка в debug_tool: {str(e)}")
        raise
```

---

## 10. Заключение

Agency Swarm v1.x предоставляет мощные возможности для создания сложных многоагентных систем. Ключ к успеху — четкое определение ролей агентов, правильная настройка коммуникации и тщательное тестирование.

### Следующие шаги

1. Изучите [официальные примеры](https://github.com/VRSEN/agency-swarm/tree/main/examples)
2. Экспериментируйте с простыми агентами
3. Постепенно усложняйте систему
4. Тестируйте каждый компонент отдельно
5. Используйте логирование для отладки

### Полезные ссылки

- [GitHub репозиторий](https://github.com/VRSEN/agency-swarm)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Документация по миграции](docs/migration/guide.mdx)
- [Примеры кода](examples/)

Удачи в создании ваших ИИ-агентств! 🚀
