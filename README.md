# برنامه جامع | Comprehensive-App

نرم‌افزار دسکتاپ Windows برای پایش خودکار پنجره‌های چارت، دریافت داده XAUUSD، ساخت کندل، تحلیل چندموتوره، پیش‌بینی پژوهشی ۱۵ دقیقه‌ای، نمایش Overlay مشروط، ژورنال و گزارش عملکرد. برنامه هیچ سفارشی به کارگزاری ارسال نمی‌کند.

## قابلیت‌های پیاده‌سازی‌شده

- شناسایی پنجره‌های قابل مشاهده با Windows API و OpenCV؛ پنجره‌های minimized، پوشیده‌شده یا بعضی سطوح hardware-accelerated قابل تضمین نیستند.
- استخراج هندسه کندل‌ها و ROI؛ OCR اختیاری برای نماد، تایم‌فریم و قیمت‌های محور با Tesseract.
- استخراج OHLC تصویری تخمینی تنها پس از کالیبراسیون؛ این تخمین هرگز به کندل‌های قابل معامله/SQLite اضافه نمی‌شود.
- دریافت تیک زنده XAUUSD از BiQuote SignalR، fallback محدود REST و رد quote کهنه/بسته/نامعتبر.
- bootstrap تاریخچه کندل‌های بسته‌شده BiQuote برای M1/M5/M15/H1/H4؛ ساخت کندل‌های محلی M1/M5/M10/M15/H1/H4 از تیک‌های تازه.
- ذخیره SQLite با جداسازی منبع‌ها؛ موتور تحلیل در هر اجرا فقط یک منبع مستقل را انتخاب می‌کند و کندل‌های Spot و Broker را با هم مخلوط نمی‌کند.
- پایش مرجع Spot از XAUS و Corgano فقط وقتی quote بروکر تازه است؛ این منابع فقط برای کنترل اختلاف‌اند و جای Bid/Ask را نمی‌گیرند.
- مغزهای تکنیکال، پرایس‌اکشن، آمار نوسان و proxy نقدینگی با شواهد و وزن‌های شفاف.
- مدل Logistic Regression سبک با جداسازی زمانی train/holdout، گزارش Accuracy/Brier و ذخیره محلی مدل؛ فقط برای نماد/تایم‌فریم/منبع آموزشی خودش فعال می‌شود.
- فشار خرید/فروش مبتنی بر جهت تغییر mid تیک؛ این داده order book یا aggressor واقعی نیست.
- خبرهای بازار، تقویم اقتصادی بااهمیت BiQuote، RSS دلخواه و هشدار رویداد high-impact نزدیک افق پیش‌بینی.
- مسیر ۱۵ نقطه‌ای یک‌دقیقه‌ای، زون‌های استاتیک/داینامیک، تاریخچه تحلیل، ژورنال دستی، screenshot انتخابی و گزارش عملکرد بر حسب R.
- Overlay شفاف و mouse-through؛ به‌روزرسانی دوره‌ای و نمایش فقط در صورت شناسایی XAUUSD/M1، دو برچسب معتبر محور قیمت و فاصله‌گذاری منظم کندل‌ها.

## نصب و اجرا

Python 3.12 روی GitHub Actions آزمایش می‌شود. سازگاری Python 3.15 هنوز تأیید نشده است.

    git clone https://github.com/mohammadrahimi137000/Comprehensive-App.git
    cd Comprehensive-App
    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    python main.py

### فعال‌سازی OCR

pytesseract با pip نصب می‌شود، اما خود برنامه Tesseract OCR باید جداگانه روی Windows نصب شود. در صفحه «تنظیمات» مسیر tesseract.exe را وارد کنید. اگر Tesseract نصب نباشد یا محور قیمت خوانده نشود، تشخیص پنجره همچنان کار می‌کند ولی کالیبراسیون و Overlay غیرفعال می‌ماند.

## تست و ساخت فایل اجرایی

    python -m pytest -q
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\build_windows.ps1

فایل‌های خروجی PyInstaller در dist/ComprehensiveApp/ قرار می‌گیرند. Workflow «Windows executable» نیز از GitHub Actions قابل اجراست. Tesseract باینری باید جداگانه روی رایانه مقصد نصب شود.

## ماژول‌های مهم

| فایل | مسئولیت |
|---|---|
| main.py | داشبورد، اتصال سرویس‌ها و چرخه عمر برنامه |
| auto_chart_detector.py, chart_vision.py, chart_recognition.py | شناسایی پنجره، ROI، OCR و تخمین OHLC تصویری |
| biquote_stream.py, resilient_feed.py, provider_clients.py | SignalR، fallback و کلاینت‌های داده |
| history_bootstrap.py, candle_builder.py, live_market_pipeline.py, market_store.py | تاریخچه، ساخت کندل و SQLite |
| analysis_engine.py, analysis_brains.py, structure_engine.py, analysis_service.py | تحلیل و سناریوها |
| ml_engine.py, tick_flow.py, news_engine.py, reference_monitor.py | ML، فشار تیک، خبر/تقویم و مرجع Spot |
| chart_projection.py, forecast_overlay.py | نگاشت و رسم مسیر پیش‌بینی |
| trade_journal.py, performance_engine.py | ژورنال و گزارش عملکرد |
| tests/ | تست‌های خودکار |

## محدودیت‌های مهم و صادقانه

- OCR در همه پلتفرم‌ها، زبان‌ها، تم‌ها و زوم‌ها قابل تضمین نیست. برای جلوگیری از رسم گمراه‌کننده، در صورت کالیبراسیون نامعتبر Overlay خاموش می‌ماند.
- OHLC حاصل از تصویر فقط تخمین هندسی است. تحلیل قیمت به کندل‌های مستقل BiQuote متکی است، نه مقادیر OCR.
- وزن مغزها فعلاً وزن اولیه ثابت است؛ یادگیری وزن بر اساس عملکرد بلندمدت و کالیبراسیون آماری احتمال‌ها هنوز به ارزیابی خارج از نمونه و داده زنده بیشتر نیاز دارد.
- مدل ML فعلی baseline پژوهشی با یک holdout زمانی است؛ تضمین سود یا مزیت معاملاتی نیست.
- داده order book/L2 و aggressor واقعی در feed موجود نیست؛ liquidity و tick pressure فقط proxy هستند.
- خبرها و تقویم اقتصادی context و هشدار رویدادند، نه مدل علّی اثر خبر بر قیمت طلا.
- منابع Spot مستقل فقط اختلاف قیمت را نشان می‌دهند و جایگزین quote بروکر نمی‌شوند.
- CI کد و تست‌های خودکار را بررسی می‌کند، اما اتصال واقعی SignalR، نصب Tesseract، capture چندمانیتوره و هم‌ترازی Overlay باید روی Windows کاربر و در زمان باز بودن بازار آزمایش شود.

## حریم خصوصی

پردازش تصویر روی رایانه محلی انجام می‌شود. OCR دوره‌ای از capture حافظه‌ای استفاده می‌کند و screenshot فایل فقط با اقدام کاربر برای ژورنال ذخیره می‌شود. کندل‌ها، مدل آموزش‌دیده و ژورنال در پوشه data/ محلی می‌مانند. درخواست‌های شبکه فقط برای دریافت quote، OHLC تاریخی، خبر، تقویم و مرجع Spot هستند.
