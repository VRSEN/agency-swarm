# Практические примеры Agency Swarm

Этот документ содержит готовые к использованию примеры для различных сценариев применения Agency Swarm.

## Содержание

1. [Система обработки заказов](#система-обработки-заказов)
2. [Аналитическая платформа](#аналитическая-платформа)
3. [Система управления контентом](#система-управления-контентом)
4. [Финансовый консультант](#финансовый-консультант)
5. [Система поддержки клиентов](#система-поддержки-клиентов)

---

## Система обработки заказов

Полная система для обработки заказов в интернет-магазине.

```python
import asyncio
from datetime import datetime
from typing import Dict, Any
from pydantic import BaseModel, Field
from agency_swarm import Agency, Agent, function_tool, RunContextWrapper, MasterContext

# Модели данных
class Order(BaseModel):
    order_id: str
    customer_id: str
    items: list[Dict[str, Any]]
    total_amount: float
    status: str = "pending"

class PaymentResult(BaseModel):
    success: bool
    transaction_id: str = None
    error_message: str = None

# Инструменты для работы с заказами
@function_tool
async def validate_order(
    ctx: RunContextWrapper[MasterContext],
    order_data: Dict[str, Any]
) -> str:
    """Валидирует данные заказа."""
    try:
        order = Order(**order_data)
        
        # Сохраняем заказ в контекст
        ctx.context.set(f"order_{order.order_id}", order.dict())
        
        return f"Заказ {order.order_id} успешно валидирован. Сумма: {order.total_amount} руб."
    except Exception as e:
        return f"Ошибка валидации заказа: {str(e)}"

@function_tool
async def check_inventory(
    ctx: RunContextWrapper[MasterContext],
    order_id: str
) -> str:
    """Проверяет наличие товаров на складе."""
    order_data = ctx.context.get(f"order_{order_id}")
    if not order_data:
        return f"Заказ {order_id} не найден"
    
    # Имитация проверки склада
    available_items = []
    unavailable_items = []
    
    for item in order_data["items"]:
        # Простая логика проверки (в реальности - запрос к БД)
        if item["quantity"] <= 10:  # Предполагаем, что на складе есть до 10 единиц
            available_items.append(item["name"])
        else:
            unavailable_items.append(item["name"])
    
    if unavailable_items:
        return f"Недостаточно товаров на складе: {', '.join(unavailable_items)}"
    
    return f"Все товары в наличии: {', '.join(available_items)}"

@function_tool
async def process_payment(
    ctx: RunContextWrapper[MasterContext],
    order_id: str,
    payment_method: str
) -> str:
    """Обрабатывает платеж."""
    order_data = ctx.context.get(f"order_{order_id}")
    if not order_data:
        return f"Заказ {order_id} не найден"
    
    # Имитация обработки платежа
    import random
    success = random.choice([True, True, True, False])  # 75% успеха
    
    if success:
        transaction_id = f"txn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        result = PaymentResult(success=True, transaction_id=transaction_id)
        
        # Обновляем статус заказа
        order_data["status"] = "paid"
        ctx.context.set(f"order_{order_id}", order_data)
        
        return f"Платеж успешно обработан. ID транзакции: {transaction_id}"
    else:
        result = PaymentResult(success=False, error_message="Недостаточно средств")
        return f"Ошибка платежа: {result.error_message}"

@function_tool
async def create_shipping_label(
    ctx: RunContextWrapper[MasterContext],
    order_id: str,
    shipping_address: str
) -> str:
    """Создает этикетку для доставки."""
    order_data = ctx.context.get(f"order_{order_id}")
    if not order_data:
        return f"Заказ {order_id} не найден"
    
    if order_data["status"] != "paid":
        return f"Заказ {order_id} не оплачен. Невозможно создать этикетку."
    
    # Имитация создания этикетки
    tracking_number = f"TRACK_{order_id}_{datetime.now().strftime('%Y%m%d')}"
    
    # Обновляем статус заказа
    order_data["status"] = "shipped"
    order_data["tracking_number"] = tracking_number
    ctx.context.set(f"order_{order_id}", order_data)
    
    return f"Этикетка создана. Номер отслеживания: {tracking_number}"

@function_tool
async def send_notification(
    ctx: RunContextWrapper[MasterContext],
    order_id: str,
    notification_type: str
) -> str:
    """Отправляет уведомление клиенту."""
    order_data = ctx.context.get(f"order_{order_id}")
    if not order_data:
        return f"Заказ {order_id} не найден"
    
    notifications = {
        "order_confirmed": f"Заказ {order_id} подтвержден",
        "payment_received": f"Платеж по заказу {order_id} получен", 
        "shipped": f"Заказ {order_id} отправлен. Трек-номер: {order_data.get('tracking_number', 'N/A')}"
    }
    
    message = notifications.get(notification_type, "Неизвестный тип уведомления")
    return f"Уведомление отправлено: {message}"

# Определение агентов
order_validator = Agent(
    name="OrderValidator",
    instructions="""
    Ты специалист по валидации заказов. Твои задачи:
    1. Проверяй корректность данных заказа
    2. Валидируй формат и обязательные поля
    3. Сохраняй валидные заказы в контекст
    
    Используй инструмент validate_order для проверки заказов.
    """,
    tools=[validate_order]
)

inventory_manager = Agent(
    name="InventoryManager", 
    instructions="""
    Ты менеджер склада. Твои задачи:
    1. Проверяй наличие товаров на складе
    2. Резервируй товары для заказов
    3. Уведомляй о недостатке товаров
    
    Используй инструмент check_inventory для проверки наличия.
    """,
    tools=[check_inventory]
)

payment_processor = Agent(
    name="PaymentProcessor",
    instructions="""
    Ты процессор платежей. Твои задачи:
    1. Обрабатывай платежи по заказам
    2. Проверяй различные способы оплаты
    3. Обновляй статус заказа после успешной оплаты
    
    Используй инструмент process_payment для обработки платежей.
    """,
    tools=[process_payment]
)

shipping_manager = Agent(
    name="ShippingManager",
    instructions="""
    Ты менеджер доставки. Твои задачи:
    1. Создавай этикетки для доставки
    2. Генерируй номера отслеживания
    3. Обновляй статус заказа на "отправлен"
    
    Используй инструмент create_shipping_label для создания этикеток.
    """,
    tools=[create_shipping_label]
)

notification_service = Agent(
    name="NotificationService",
    instructions="""
    Ты сервис уведомлений. Твои задачи:
    1. Отправляй уведомления клиентам
    2. Информируй о статусе заказа
    3. Отправляй подтверждения и трек-номера
    
    Используй инструмент send_notification для отправки уведомлений.
    """,
    tools=[send_notification]
)

order_coordinator = Agent(
    name="OrderCoordinator",
    instructions="""
    Ты координатор заказов. Управляешь всем процессом обработки заказа:
    
    1. Получи заказ и попроси OrderValidator валидировать его
    2. Попроси InventoryManager проверить наличие товаров
    3. Если товары есть, попроси PaymentProcessor обработать платеж
    4. После успешной оплаты попроси ShippingManager создать этикетку
    5. Попроси NotificationService отправить уведомления на каждом этапе
    
    Координируй работу всех агентов и следи за статусом заказа.
    """,
    tools=[]
)

# Создание агентства
order_processing_agency = Agency(
    order_coordinator,
    communication_flows=[
        order_coordinator > order_validator,
        order_coordinator > inventory_manager,
        order_coordinator > payment_processor,
        order_coordinator > shipping_manager,
        order_coordinator > notification_service
    ],
    shared_instructions="Обрабатывай заказы быстро и точно. Всегда информируй клиента о статусе."
)

# Пример использования
async def process_order_example():
    """Пример обработки заказа."""
    
    # Данные заказа
    order_data = {
        "order_id": "ORD_001",
        "customer_id": "CUST_123", 
        "items": [
            {"name": "Ноутбук", "quantity": 1, "price": 50000},
            {"name": "Мышь", "quantity": 2, "price": 1000}
        ],
        "total_amount": 52000
    }
    
    message = f"""
    Обработай новый заказ:
    
    Данные заказа: {order_data}
    Способ оплаты: банковская карта
    Адрес доставки: г. Москва, ул. Примерная, д. 1
    
    Выполни полный цикл обработки заказа.
    """
    
    print("🛒 Начинаем обработку заказа...")
    response = await order_processing_agency.get_response(message)
    print(f"✅ Результат: {response.final_output}")

if __name__ == "__main__":
    asyncio.run(process_order_example())
```

---

## Аналитическая платформа

Система для анализа данных и создания отчетов.

```python
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from io import StringIO
import base64
from pydantic import BaseModel
from agency_swarm import Agency, Agent, function_tool, RunContextWrapper, MasterContext

class AnalysisReport(BaseModel):
    summary: str
    key_metrics: dict
    recommendations: list[str]
    chart_data: str = None

@function_tool
async def load_data(
    ctx: RunContextWrapper[MasterContext],
    data_source: str,
    query: str = None
) -> str:
    """Загружает данные из различных источников."""
    
    # Имитация загрузки данных
    if data_source == "sales_db":
        # Генерируем примерные данные продаж
        import random
        from datetime import datetime, timedelta
        
        data = []
        for i in range(100):
            date = datetime.now() - timedelta(days=random.randint(0, 365))
            data.append({
                "date": date.strftime("%Y-%m-%d"),
                "product": random.choice(["Товар A", "Товар B", "Товар C"]),
                "sales": random.randint(1000, 10000),
                "region": random.choice(["Москва", "СПб", "Екатеринбург"])
            })
        
        # Сохраняем данные в контекст
        ctx.context.set("current_dataset", data)
        return f"Загружено {len(data)} записей из {data_source}"
    
    elif data_source == "user_analytics":
        # Генерируем данные пользователей
        data = []
        for i in range(50):
            data.append({
                "user_id": f"user_{i}",
                "sessions": random.randint(1, 20),
                "page_views": random.randint(5, 100),
                "conversion": random.choice([True, False])
            })
        
        ctx.context.set("current_dataset", data)
        return f"Загружено {len(data)} записей пользовательской аналитики"
    
    return f"Неизвестный источник данных: {data_source}"

@function_tool
async def analyze_data(
    ctx: RunContextWrapper[MasterContext],
    analysis_type: str
) -> str:
    """Выполняет анализ загруженных данных."""
    
    data = ctx.context.get("current_dataset")
    if not data:
        return "Нет загруженных данных для анализа"
    
    df = pd.DataFrame(data)
    
    if analysis_type == "descriptive":
        # Описательная статистика
        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
        stats = df[numeric_cols].describe().to_dict()
        
        ctx.context.set("analysis_results", {
            "type": "descriptive",
            "statistics": stats,
            "row_count": len(df),
            "columns": list(df.columns)
        })
        
        return f"Выполнен описательный анализ. Строк: {len(df)}, столбцов: {len(df.columns)}"
    
    elif analysis_type == "trend":
        # Анализ трендов (если есть данные по датам)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            if "sales" in df.columns:
                trend_data = df.groupby("date")["sales"].sum().reset_index()
                trend_analysis = {
                    "total_sales": trend_data["sales"].sum(),
                    "avg_daily_sales": trend_data["sales"].mean(),
                    "max_sales_day": trend_data.loc[trend_data["sales"].idxmax(), "date"].strftime("%Y-%m-%d"),
                    "min_sales_day": trend_data.loc[trend_data["sales"].idxmin(), "date"].strftime("%Y-%m-%d")
                }
                
                ctx.context.set("analysis_results", {
                    "type": "trend",
                    "trend_data": trend_analysis
                })
                
                return f"Анализ трендов завершен. Общие продажи: {trend_analysis['total_sales']}"
        
        return "Недостаточно данных для анализа трендов"
    
    return f"Неизвестный тип анализа: {analysis_type}"

@function_tool
async def create_visualization(
    ctx: RunContextWrapper[MasterContext],
    chart_type: str,
    title: str = "График"
) -> str:
    """Создает визуализацию данных."""
    
    data = ctx.context.get("current_dataset")
    if not data:
        return "Нет данных для визуализации"
    
    df = pd.DataFrame(data)
    
    try:
        plt.figure(figsize=(10, 6))
        
        if chart_type == "bar" and "product" in df.columns and "sales" in df.columns:
            # Столбчатая диаграмма продаж по продуктам
            product_sales = df.groupby("product")["sales"].sum()
            plt.bar(product_sales.index, product_sales.values)
            plt.xlabel("Продукт")
            plt.ylabel("Продажи")
            
        elif chart_type == "line" and "date" in df.columns and "sales" in df.columns:
            # Линейный график продаж по времени
            df["date"] = pd.to_datetime(df["date"])
            daily_sales = df.groupby("date")["sales"].sum().reset_index()
            plt.plot(daily_sales["date"], daily_sales["sales"])
            plt.xlabel("Дата")
            plt.ylabel("Продажи")
            plt.xticks(rotation=45)
            
        elif chart_type == "pie" and "region" in df.columns and "sales" in df.columns:
            # Круговая диаграмма продаж по регионам
            region_sales = df.groupby("region")["sales"].sum()
            plt.pie(region_sales.values, labels=region_sales.index, autopct='%1.1f%%')
            
        else:
            return f"Невозможно создать график типа {chart_type} с доступными данными"
        
        plt.title(title)
        plt.tight_layout()
        
        # Сохраняем график в base64
        from io import BytesIO
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        chart_base64 = base64.b64encode(buffer.getvalue()).decode()
        plt.close()
        
        ctx.context.set("last_chart", chart_base64)
        return f"График '{title}' создан успешно"
        
    except Exception as e:
        return f"Ошибка создания графика: {str(e)}"

@function_tool
async def generate_report(
    ctx: RunContextWrapper[MasterContext],
    report_title: str
) -> str:
    """Генерирует итоговый отчет."""
    
    analysis_results = ctx.context.get("analysis_results")
    chart_data = ctx.context.get("last_chart")
    
    if not analysis_results:
        return "Нет результатов анализа для создания отчета"
    
    # Создаем структурированный отчет
    if analysis_results["type"] == "descriptive":
        summary = f"Проанализировано {analysis_results['row_count']} записей"
        key_metrics = analysis_results["statistics"]
        recommendations = [
            "Рекомендуется провести дополнительный анализ трендов",
            "Изучить корреляции между переменными",
            "Провести сегментацию данных"
        ]
    
    elif analysis_results["type"] == "trend":
        trend_data = analysis_results["trend_data"]
        summary = f"Общие продажи составили {trend_data['total_sales']}"
        key_metrics = trend_data
        recommendations = [
            "Увеличить маркетинговые усилия в дни с низкими продажами",
            "Изучить факторы успеха в дни с высокими продажами",
            "Разработать стратегию для поддержания роста"
        ]
    
    else:
        summary = "Анализ завершен"
        key_metrics = {}
        recommendations = []
    
    report = AnalysisReport(
        summary=summary,
        key_metrics=key_metrics,
        recommendations=recommendations,
        chart_data=chart_data
    )
    
    ctx.context.set("final_report", report.dict())
    
    return f"Отчет '{report_title}' сгенерирован. Основные выводы: {summary}"

# Определение агентов
data_loader = Agent(
    name="DataLoader",
    instructions="""
    Ты специалист по загрузке данных. Твои задачи:
    1. Подключайся к различным источникам данных
    2. Загружай данные по запросам
    3. Проверяй качество загруженных данных
    
    Используй инструмент load_data для загрузки данных.
    """,
    tools=[load_data]
)

data_analyst = Agent(
    name="DataAnalyst", 
    instructions="""
    Ты аналитик данных. Твои задачи:
    1. Выполняй различные виды анализа данных
    2. Вычисляй статистики и метрики
    3. Выявляй паттерны и тренды
    
    Используй инструмент analyze_data для анализа.
    """,
    tools=[analyze_data]
)

visualization_specialist = Agent(
    name="VisualizationSpecialist",
    instructions="""
    Ты специалист по визуализации данных. Твои задачи:
    1. Создавай информативные графики и диаграммы
    2. Выбирай подходящие типы визуализации
    3. Делай графики понятными и красивыми
    
    Используй инструмент create_visualization для создания графиков.
    """,
    tools=[create_visualization]
)

report_generator = Agent(
    name="ReportGenerator",
    instructions="""
    Ты генератор отчетов. Твои задачи:
    1. Создавай структурированные отчеты
    2. Формулируй выводы и рекомендации
    3. Объединяй результаты анализа и визуализации
    
    Используй инструмент generate_report для создания отчетов.
    """,
    tools=[generate_report],
    output_type=AnalysisReport
)

analytics_coordinator = Agent(
    name="AnalyticsCoordinator",
    instructions="""
    Ты координатор аналитической платформы. Управляешь процессом анализа:
    
    1. Определи источник данных и попроси DataLoader загрузить данные
    2. Попроси DataAnalyst выполнить нужный тип анализа
    3. Попроси VisualizationSpecialist создать подходящие графики
    4. Попроси ReportGenerator создать итоговый отчет
    
    Координируй работу всех специалистов для получения полного анализа.
    """,
    tools=[]
)

# Создание агентства
analytics_agency = Agency(
    analytics_coordinator,
    communication_flows=[
        analytics_coordinator > data_loader,
        analytics_coordinator > data_analyst,
        analytics_coordinator > visualization_specialist,
        analytics_coordinator > report_generator
    ],
    shared_instructions="Создавай точные и полезные аналитические отчеты."
)

# Пример использования
async def analytics_example():
    """Пример аналитического запроса."""
    
    message = """
    Проведи анализ продаж:
    
    1. Загрузи данные из sales_db
    2. Выполни анализ трендов продаж
    3. Создай столбчатую диаграмму продаж по продуктам
    4. Сгенерируй отчет "Анализ продаж за период"
    
    Мне нужен полный анализ с выводами и рекомендациями.
    """
    
    print("📊 Начинаем аналитический процесс...")
    response = await analytics_agency.get_response(message)
    print(f"✅ Результат: {response.final_output}")

if __name__ == "__main__":
    asyncio.run(analytics_example())
```

---

## Система управления контентом

Автоматизированная система для создания и управления контентом.

```python
import asyncio
from datetime import datetime
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from agency_swarm import Agency, Agent, function_tool, RunContextWrapper, MasterContext

class ContentPiece(BaseModel):
    title: str
    content: str
    content_type: str  # "blog_post", "social_media", "email"
    target_audience: str
    keywords: List[str]
    tone: str  # "professional", "casual", "friendly"
    status: str = "draft"

class SEOAnalysis(BaseModel):
    keyword_density: Dict[str, float]
    readability_score: int
    meta_description: str
    recommendations: List[str]

@function_tool
async def research_topic(
    ctx: RunContextWrapper[MasterContext],
    topic: str,
    target_audience: str
) -> str:
    """Исследует тему для создания контента."""
    
    # Имитация исследования темы
    research_data = {
        "topic": topic,
        "target_audience": target_audience,
        "key_points": [
            f"Основные аспекты темы '{topic}'",
            f"Интересы аудитории '{target_audience}'",
            "Актуальные тренды в области",
            "Конкурентный анализ"
        ],
        "keywords": [
            topic.lower(),
            f"{topic} для {target_audience}",
            f"как {topic}",
            f"{topic} советы"
        ],
        "sources": [
            "Отраслевые исследования",
            "Анализ конкурентов", 
            "Пользовательские запросы"
        ]
    }
    
    ctx.context.set(f"research_{topic}", research_data)
    
    return f"Исследование темы '{topic}' завершено. Найдено {len(research_data['key_points'])} ключевых аспектов."

@function_tool
async def create_content(
    ctx: RunContextWrapper[MasterContext],
    topic: str,
    content_type: str,
    tone: str = "professional"
) -> str:
    """Создает контент на основе исследования."""
    
    research_data = ctx.context.get(f"research_{topic}")
    if not research_data:
        return f"Нет данных исследования для темы '{topic}'. Сначала проведите исследование."
    
    # Генерация контента на основе исследования
    if content_type == "blog_post":
        title = f"Полное руководство по {topic}"
        content = f"""
# {title}

## Введение
{topic} становится все более важным для {research_data['target_audience']}. 
В этой статье мы рассмотрим ключевые аспекты и дадим практические советы.

## Основные моменты
{chr(10).join([f"- {point}" for point in research_data['key_points']])}

## Практические советы
1. Изучите основы {topic}
2. Применяйте полученные знания на практике
3. Следите за новыми тенденциями
4. Анализируйте результаты

## Заключение
{topic} - это важная область, которая требует постоянного изучения и практики.
        """
    
    elif content_type == "social_media":
        title = f"{topic} - ключевые моменты"
        content = f"""
🔥 {topic} для {research_data['target_audience']}!

✅ {research_data['key_points'][0]}
✅ {research_data['key_points'][1]}
✅ {research_data['key_points'][2]}

💡 Хотите узнать больше? Читайте наш блог!

#{topic.replace(' ', '')} #советы #обучение
        """
    
    elif content_type == "email":
        title = f"Новости о {topic}"
        content = f"""
Привет!

Сегодня хотим поделиться важной информацией о {topic}.

{research_data['key_points'][0]}

Это особенно актуально для {research_data['target_audience']}, потому что:
- {research_data['key_points'][1]}
- {research_data['key_points'][2]}

Подробнее читайте в нашем блоге.

С уважением,
Команда контент-маркетинга
        """
    
    else:
        return f"Неподдерживаемый тип контента: {content_type}"
    
    # Создаем объект контента
    content_piece = ContentPiece(
        title=title,
        content=content,
        content_type=content_type,
        target_audience=research_data['target_audience'],
        keywords=research_data['keywords'],
        tone=tone
    )
    
    # Сохраняем в контекст
    content_id = f"content_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    ctx.context.set(content_id, content_piece.dict())
    ctx.context.set("last_content_id", content_id)
    
    return f"Контент создан: '{title}' ({content_type}). ID: {content_id}"

@function_tool
async def optimize_seo(
    ctx: RunContextWrapper[MasterContext],
    content_id: str = None
) -> str:
    """Оптимизирует контент для SEO."""
    
    if not content_id:
        content_id = ctx.context.get("last_content_id")
    
    if not content_id:
        return "Не указан ID контента для оптимизации"
    
    content_data = ctx.context.get(content_id)
    if not content_data:
        return f"Контент с ID {content_id} не найден"
    
    content = content_data["content"]
    keywords = content_data["keywords"]
    
    # Простой анализ SEO
    word_count = len(content.split())
    
    # Подсчет плотности ключевых слов
    keyword_density = {}
    for keyword in keywords:
        count = content.lower().count(keyword.lower())
        density = (count / word_count) * 100 if word_count > 0 else 0
        keyword_density[keyword] = round(density, 2)
    
    # Оценка читаемости (упрощенная)
    sentences = content.count('.') + content.count('!') + content.count('?')
    avg_words_per_sentence = word_count / sentences if sentences > 0 else 0
    readability_score = max(0, min(100, 100 - (avg_words_per_sentence - 15) * 2))
    
    # Генерация мета-описания
    first_paragraph = content.split('\n')[0][:150] + "..."
    
    # Рекомендации
    recommendations = []
    if max(keyword_density.values()) < 1:
        recommendations.append("Увеличьте плотность ключевых слов")
    if max(keyword_density.values()) > 3:
        recommendations.append("Уменьшите плотность ключевых слов")
    if readability_score < 60:
        recommendations.append("Упростите текст для лучшей читаемости")
    if word_count < 300:
        recommendations.append("Увеличьте объем контента")
    
    seo_analysis = SEOAnalysis(
        keyword_density=keyword_density,
        readability_score=int(readability_score),
        meta_description=first_paragraph,
        recommendations=recommendations
    )
    
    # Обновляем контент с SEO данными
    content_data["seo_analysis"] = seo_analysis.dict()
    ctx.context.set(content_id, content_data)
    
    return f"SEO анализ завершен. Читаемость: {readability_score}/100. Рекомендаций: {len(recommendations)}"

@function_tool
async def schedule_publication(
    ctx: RunContextWrapper[MasterContext],
    content_id: str,
    publication_date: str,
    platform: str
) -> str:
    """Планирует публикацию контента."""
    
    content_data = ctx.context.get(content_id)
    if not content_data:
        return f"Контент с ID {content_id} не найден"
    
    # Обновляем статус и планируем публикацию
    content_data["status"] = "scheduled"
    content_data["publication_date"] = publication_date
    content_data["platform"] = platform
    
    ctx.context.set(content_id, content_data)
    
    return f"Контент '{content_data['title']}' запланирован к публикации {publication_date} на {platform}"

# Определение агентов
content_researcher = Agent(
    name="ContentResearcher",
    instructions="""
    Ты исследователь контента. Твои задачи:
    1. Исследуй темы для создания контента
    2. Анализируй целевую аудиторию
    3. Находи ключевые слова и тренды
    4. Изучай конкурентов
    
    Используй инструмент research_topic для исследования тем.
    """,
    tools=[research_topic]
)

content_creator = Agent(
    name="ContentCreator",
    instructions="""
    Ты создатель контента. Твои задачи:
    1. Создавай качественный контент на основе исследований
    2. Адаптируй контент под разные форматы
    3. Поддерживай нужный тон и стиль
    4. Учитывай потребности целевой аудитории
    
    Используй инструмент create_content для создания контента.
    """,
    tools=[create_content]
)

seo_specialist = Agent(
    name="SEOSpecialist",
    instructions="""
    Ты SEO специалист. Твои задачи:
    1. Оптимизируй контент для поисковых систем
    2. Анализируй плотность ключевых слов
    3. Проверяй читаемость текста
    4. Создавай мета-описания
    5. Давай рекомендации по улучшению
    
    Используй инструмент optimize_seo для SEO оптимизации.
    """,
    tools=[optimize_seo]
)

content_manager = Agent(
    name="ContentManager",
    instructions="""
    Ты менеджер контента. Твои задачи:
    1. Планируй публикацию контента
    2. Управляй календарем контента
    3. Координируй работу команды
    4. Отслеживай статусы контента
    
    Используй инструмент schedule_publication для планирования публикаций.
    """,
    tools=[schedule_publication]
)

content_director = Agent(
    name="ContentDirector",
    instructions="""
    Ты директор по контенту. Управляешь всем процессом создания контента:
    
    1. Получи запрос на создание контента
    2. Попроси ContentResearcher исследовать тему
    3. Попроси ContentCreator создать контент
    4. Попроси SEOSpecialist оптимизировать контент
    5. Попроси ContentManager запланировать публикацию
    
    Координируй работу всей команды для создания качественного контента.
    """,
    tools=[]
)

# Создание агентства
content_agency = Agency(
    content_director,
    communication_flows=[
        content_director > content_researcher,
        content_director > content_creator,
        content_director > seo_specialist,
        content_director > content_manager
    ],
    shared_instructions="Создавай качественный, оптимизированный контент для целевой аудитории."
)

# Пример использования
async def content_creation_example():
    """Пример создания контента."""
    
    message = """
    Создай контент-план для блога:
    
    Тема: "Искусственный интеллект в бизнесе"
    Целевая аудитория: "руководители малого и среднего бизнеса"
    Тип контента: blog_post
    Тон: professional
    
    Нужно:
    1. Исследовать тему
    2. Создать статью для блога
    3. Оптимизировать для SEO
    4. Запланировать публикацию на завтра на корпоративном блоге
    
    Также создай пост для социальных сетей на ту же тему.
    """
    
    print("📝 Начинаем создание контента...")
    response = await content_agency.get_response(message)
    print(f"✅ Результат: {response.final_output}")

if __name__ == "__main__":
    asyncio.run(content_creation_example())
```

Этот документ содержит три полных примера систем, построенных на Agency Swarm. Каждый пример демонстрирует:

1. **Специализированные агенты** с четкими ролями
2. **Координирующий агент** для управления процессом
3. **Инструменты** для выполнения конкретных задач
4. **Обмен данными** через MasterContext
5. **Структурированные выходы** с Pydantic моделями
6. **Реальные сценарии использования**

Каждая система может быть адаптирована под конкретные потребности и интегрирована с реальными API и базами данных.
