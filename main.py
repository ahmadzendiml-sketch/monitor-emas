import asyncio
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import httpx
from bs4 import BeautifulSoup

history = []
last_buy = None
active_connections = set()
usd_idr_history = []

update_event = asyncio.Event()
usd_idr_update_event = asyncio.Event()

def format_rupiah(nominal):
    try:
        return "{:,}".format(int(nominal)).replace(",", ".")
    except:
        return str(nominal)

def parse_price_to_float(price_str):
    try:
        return float(price_str.replace('.', '').replace(',', '.'))
    except:
        return None

async def fetch_usd_idr_price():
    url = "https://www.google.com/finance/quote/USD-IDR"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            price_div = soup.find("div", class_="YMlKec fxKbKc")
            if price_div:
                return price_div.text.strip()
    except Exception as e:
        print("Error fetching USD/IDR price:", e)
    return None

async def api_loop():
    global last_buy, history
    api_url = "https://api.treasury.id/api/v1/antigrvty/gold/rate"
    shown_updates = set()
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                response = await client.post(api_url)
                if response.status_code == 200:
                    data = response.json().get("data", {})
                    buying_rate = int(data.get("buying_rate", 0))
                    selling_rate = int(data.get("selling_rate", 0))
                    updated_at = data.get("updated_at")
                    if updated_at and updated_at not in shown_updates:
                        status = "➖ Tetap"
                        if last_buy is not None:
                            if buying_rate > last_buy:
                                status = "🚀 Naik"
                            elif buying_rate < last_buy:
                                status = "🔻 Turun"
                        row = {
                            "buying_rate": buying_rate,
                            "selling_rate": selling_rate,
                            "status": status,
                            "created_at": updated_at
                        }
                        history.append(row)
                        history[:] = history[-1441:]
                        last_buy = buying_rate
                        shown_updates.add(updated_at)
                        update_event.set()
                await asyncio.sleep(0.5)
            except Exception as e:
                print("Error in api_loop:", e)
                await asyncio.sleep(1)

async def usd_idr_loop():
    global usd_idr_history
    while True:
        try:
            price_str = await fetch_usd_idr_price()
            if price_str:
                price_float = parse_price_to_float(price_str)
                if price_float is not None:
                    if not usd_idr_history or usd_idr_history[-1]["price"] != price_str:
                        wib_now = datetime.utcnow() + timedelta(hours=7)
                        usd_idr_history.append({
                            "price": price_str,
                            "time": wib_now.strftime("%H:%M:%S")
                        })
                        usd_idr_history[:] = usd_idr_history[-11:]
                        usd_idr_update_event.set()
            await asyncio.sleep(1)
        except Exception as e:
            print("Error in usd_idr_loop:", e)
            await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task1 = asyncio.create_task(api_loop())
    task2 = asyncio.create_task(usd_idr_loop())
    yield
    task1.cancel()
    task2.cancel()

app = FastAPI(lifespan=lifespan)

html = """ 
<!DOCTYPE html>
<html>
<head>
    <title>Harga Emas Treasury</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css"/>
    <style>
        body { font-family: Arial; margin: 40px; background: #fff; color: #222; transition: background 0.3s, color 0.3s; }
        table.dataTable thead th { font-weight: bold; }
        th.waktu, td.waktu {
            width: 150px;
            min-width: 100px;
            max-width: 180px;
            white-space: nowrap;
            text-align: left;
        }
        th.profit, td.profit {
            width: 100px;
            min-width: 100px;
            max-width: 120px;
            white-space: nowrap;
            text-align: left;
        }
        .dark-mode { background: #181a1b !important; color: #e0e0e0 !important; }
        .dark-mode #jam { color: #ffb300 !important; }
        .dark-mode table.dataTable { background: #23272b !important; color: #e0e0e0 !important; }
        .dark-mode table.dataTable thead th { background: #23272b !important; color: #ffb300 !important; }
        .dark-mode table.dataTable tbody td { background: #23272b !important; color: #e0e0e0 !important; }
        .theme-toggle-btn {
            padding: 0;
            border: none;
            border-radius: 50%;
            background: #222;
            color: #fff;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.3s, color 0.3s;
            font-size: 1.5em;
            width: 44px;
            height: 44px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .theme-toggle-btn:hover {
            background: #444;
        }
        .dark-mode .theme-toggle-btn {
            background: #ffb300;
            color: #222;
        }
        .dark-mode .theme-toggle-btn:hover {
            background: #ffd54f;
        }
        .container-flex {
            display: flex;
            gap: 15px;
            margin-top: 10px;
        }
        #usdIdrWidget {
            overflow:hidden; height:370px; width:630px; border:1px solid #ccc; border-radius:6px;
        }
        #usdIdrRealtime {
            width: 248px;
            border: 1px solid #ccc;
            # border-radius: 6px;
            padding: 10px;
            height: 370px;
            overflow-y: auto;
        }
        #priceList li {
            margin-bottom: 1px;
        }
        .time {
            color: gray;
            font-size: 0.9em;
            margin-left: 10px;
        }
        #currentPrice {
        color: red;
        font-weight: bold;
        }
        .dark-mode #currentPrice {
            color: #00E124; text-shadow: 1px 1px #00B31C;
        }
        #tabel tbody tr:first-child td {
            color: red !important;
            font-weight: bold;
        }
        .dark-mode #tabel tbody tr:first-child td {
            color: #00E124 !important;
            font-weight: bold;
        }
        
        #footerApp {
            width: 100%;
            overflow: hidden;
            position: fixed;
            bottom: 0;
            left: 0;
            background: transparent;
            text-align: center;
            z-index: 100;
            padding: 8px 0;
        }

        .marquee-text {
            display: inline-block;
            color: #F5274D;
            animation: marquee 70s linear infinite;
            font-weight: bold;
        }
        .dark-mode .marquee-text {
            color: #B232B2;
            font-weight: bold;
        }

        @keyframes marquee {
            0%   { transform: translateX(100vw); }
            100% { transform: translateX(-100vw); }
        }
    </style>
</head>
<body>
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
        <h2 style="margin:0;">MONITORING Harga Emas Treasury</h2>
        <button class="theme-toggle-btn" id="themeBtn" onclick="toggleTheme()" title="Ganti Tema" style="margin-left:20px; font-size:1.5em; width:44px; height:44px; display:flex; align-items:center; justify-content:center;">
            🌙
        </button>
    </div>
    <div id="jam" style="font-size:1.3em; color:#ff1744; font-weight:bold; margin-bottom:15px;"></div>
    <table id="tabel" class="display" style="width:100%">
        <thead>
            <tr>
                <th class="waktu">Waktu</th>
                <th>Data Transaksi</th>
                <th class="profit">Est. cuan 20 JT</th>
                <th class="profit">Est. cuan 30 JT</th>
            </tr>
        </thead>
        <tbody></tbody>
    </table>
    <div style="margin-top:40px;">
            <h3>Chart Harga Emas (XAU/USD)</h3>
            <div id="tradingview_chart"></div>
            <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
            <script type="text/javascript">
            new TradingView.widget({
                "width": "100%",
                "height": 400,
                "symbol": "OANDA:XAUUSD",
                "interval": "15",
                "timezone": "Asia/Jakarta",
                "theme": "light",
                "style": "1",
                "locale": "id",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "hide_top_toolbar": false,
                "save_image": false,
                "container_id": "tradingview_chart"
            });
            </script>
        </div>
    <div class="container-flex">
        <div>
            <h3 style="display:block; margin-top:30px;">Harga USD/IDR Investing - Jangka Waktu 15 Menit</h3>
        <div style="overflow:hidden; height:370px; width:620px; border:1px solid #ccc; border-radius:6px;">
        <iframe 
            src="https://sslcharts.investing.com/index.php?force_lang=54&pair_ID=2138&timescale=900&candles=80&style=candles"
            width="618"
            height="430"
            style="margin-top:-62px; border:0;"
            scrolling="no"
            frameborder="0"
            allowtransparency="true">
        </iframe>
        </div>
        </div>

        <div>
            <h3>Harga USD/IDR Google Finance</h3>
            <div id="usdIdrRealtime" style="margin-top:0; padding-top:2px;">
            <p>Harga saat ini: <span id="currentPrice" style="color: red; font-weight: bold;">Loading...</span></p>
            <h4>Harga Terakhir:</h4>
            <ul id="priceList" style="list-style:none; padding-left:0; max-height:275px; overflow-y:auto;"></ul>
            </div>
        </div>
    </div>
    <h3 style="display:block; margin-top:30px;">Kalender Ekonomi</h3>
        <div style="width:630px; ">
            <iframe src="https://sslecal2.investing.com?columns=exc_flags,exc_currency,exc_importance,exc_actual,exc_forecast,exc_previous&category=_employment,_economicActivity,_inflation,_centralBanks,_confidenceIndex&importance=3&features=datepicker,timezone,timeselector,filters&countries=5,37,48,35,17,36,26,12,72&calType=week&timeZone=27&lang=54" width="650" height="467" frameborder="0" allowtransparency="true" marginwidth="0" marginheight="0"></iframe><div class="poweredBy" style="font-family: Arial, Helvetica, sans-serif;"><span style="font-size: 11px;color: #333333;text-decoration: none;">Kalender Ekonomi Real Time dipersembahkan oleh <a href="https://id.investing.com" rel="nofollow" target="_blank" style="font-size: 11px;color: #06529D; font-weight: bold;" class="underline_link">Investing.com Indonesia</a>.</span></div>        
    </div>
    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>

    <script>
        var table = $('#tabel').DataTable({
            "pageLength": 4,
            "lengthMenu": [4, 8, 18, 48, 88, 888, 1441],
            "order": [],
            "columns": [
                { "data": "waktu" },
                { "data": "all" },
                { "data": "jt20" },
                { "data": "jt30" }
            ]
        });

        function updateTable(history) {
            history.sort(function(a, b) {
                return new Date(b.created_at) - new Date(a.created_at);
            });
            var dataArr = history.map(function(d) {
                return {
                    waktu: d.created_at,
                    all: `Harga Beli: ${d.buying_rate} | Harga Jual: ${d.selling_rate} | Status: ${d.status || "➖"}`,
                    jt20: d.jt20,
                    jt30: d.jt30
                };
            });
            table.clear();
            table.rows.add(dataArr);
            table.draw(false);
            table.page('first').draw(false);
        }

        function connectWS() {
            var ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
            ws.onmessage = function(event) {
                var data = JSON.parse(event.data);
                if (data.history) updateTable(data.history);
                if (data.usd_idr_history) updateUsdIdrPrice(data.usd_idr_history);
            };
            ws.onclose = function() {
                setTimeout(connectWS, 1000);
            };
        }
        connectWS();

        function formatHargaIDR(str) {
            str = str.trim();
            let [angka, desimal] = str.split(".");
            angka = angka.replace(/,/g, ".");
            if (desimal !== undefined) {
                return angka + "," + desimal;
            } else {
                return angka;
            }
        }
        
        function updateUsdIdrPrice(history) {
            const currentPriceEl = document.getElementById("currentPrice");
            const priceListEl = document.getElementById("priceList");

            function formatHargaIDR(str) {
                str = str.trim();
                let [angka, desimal] = str.split(".");
                angka = angka.replace(/,/g, ".");
                if (desimal !== undefined) {
                    return angka + "," + desimal;
                } else {
                    return angka;
                }
            }
            let icon = "➖";
            if (history.length > 1) {
                let now = parseFloat(history[history.length - 1].price.replace(/,/g, ''));
                let prev = parseFloat(history[history.length - 2].price.replace(/,/g, ''));
                if (now > prev) icon = "🚀";
                else if (now < prev) icon = "🔻";
            }
            if(history.length > 0) {
                currentPriceEl.innerHTML = `<span id="currentPrice" >${formatHargaIDR(history[history.length - 1].price)}</span> <span>${icon}</span>`;
            }
            priceListEl.innerHTML = "";
            for (let i = history.length - 1; i >= 0; i--) {
                let rowIcon = "➖";
                if (i < history.length - 1) {
                    let now = parseFloat(history[i].price.replace(/,/g, ''));
                    let prev = parseFloat(history[i+1].price.replace(/,/g, ''));
                    if (now > prev) rowIcon = "🚀";
                    else if (now < prev) rowIcon = "🔻";
                } else if (i === history.length - 1) {
                    rowIcon = icon;
                }
                const li = document.createElement("li");
                li.textContent = formatHargaIDR(history[i].price) + " ";
                const spanTime = document.createElement("span");
                spanTime.className = "time";
                spanTime.textContent = `(${history[i].time})`;
                li.appendChild(spanTime);
                const iconSpan = document.createElement("span");
                iconSpan.className = "price-icon";
                iconSpan.textContent = " " + rowIcon;
                li.appendChild(iconSpan);

                priceListEl.appendChild(li);
            }
        }

        function updateJam() {
            var now = new Date();
            var tgl = now.toLocaleDateString('id-ID', { day: '2-digit', month: 'long', year: 'numeric' });
            var jam = now.toLocaleTimeString('id-ID', { hour12: false });
            document.getElementById("jam").textContent = tgl + " " + jam + " WIB";
        }
        setInterval(updateJam, 1000);
        updateJam();

        function toggleTheme() {
            var body = document.body;
            var btn = document.getElementById('themeBtn');
            body.classList.toggle('dark-mode');
            if (body.classList.contains('dark-mode')) {
                btn.textContent = "☀️";
                localStorage.setItem('theme', 'dark');
            } else {
                btn.textContent = "🌙";
                localStorage.setItem('theme', 'light');
            }
        }
        (function() {
            var theme = localStorage.getItem('theme');
            var btn = document.getElementById('themeBtn');
            if (theme === 'dark') {
                document.body.classList.add('dark-mode');
                btn.textContent = "☀️";
            } else {
                btn.textContent = "🌙";
            }
        })();
    </script>
<footer id="footerApp">
    <span class="marquee-text">&copy;2025 ~ahmadkholil~</span>
</footer>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(html)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    last_sent_updated_at = None
    last_usd_idr_price = None

    if history:
        last_sent_updated_at = history[-1]["created_at"]
    if usd_idr_history:
        last_usd_idr_price = usd_idr_history[-1]["price"]

    def calc_20jt(h):
        try:
            val = int((20000000 / h["buying_rate"]) * h["selling_rate"] - 19315000)
            if val > 0:
                return f"+{format_rupiah(val)} 🚀"
            elif val < 0:
                return f"-{format_rupiah(abs(val))} 🔻"
            else:
                return "0 ➖"
        except Exception:
            return "-"

    def calc_30jt(h):
        try:
            val = int((30000000 / h["buying_rate"]) * h["selling_rate"] - 28980000)
            if val > 0:
                return f"+{format_rupiah(val)} 🚀"
            elif val < 0:
                return f"-{format_rupiah(abs(val))} 🔻"
            else:
                return "0 ➖"
        except Exception:
            return "-"

    await websocket.send_text(json.dumps({
        "history": [
            {
                "buying_rate": format_rupiah(h["buying_rate"]),
                "selling_rate": format_rupiah(h["selling_rate"]),
                "status": h["status"],
                "created_at": h["created_at"],
                "jt20": calc_20jt(h) if h["buying_rate"] and h["selling_rate"] else "-",
                "jt30": calc_30jt(h) if h["buying_rate"] and h["selling_rate"] else "-"
            }
            for h in history[-1441:]
        ],
        "usd_idr_history": usd_idr_history
    }))

    try:
        while True:
            wait_tasks = [
                asyncio.create_task(update_event.wait()),
                asyncio.create_task(usd_idr_update_event.wait())
            ]
            done, pending = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()

            if update_event.is_set():
                update_event.clear()
            if usd_idr_update_event.is_set():
                usd_idr_update_event.clear()

            current_updated_at = history[-1]["created_at"] if history else None
            current_usd_idr_price = usd_idr_history[-1]["price"] if usd_idr_history else None

            send_history = False
            if current_updated_at != last_sent_updated_at:
                send_history = True
                last_sent_updated_at = current_updated_at

            if current_usd_idr_price != last_usd_idr_price:
                send_history = True
                last_usd_idr_price = current_usd_idr_price

            if send_history:
                msg = {
                    "history": [
                        {
                            "buying_rate": format_rupiah(h["buying_rate"]),
                            "selling_rate": format_rupiah(h["selling_rate"]),
                            "status": h["status"],
                            "created_at": h["created_at"],
                            "jt20": calc_20jt(h) if h["buying_rate"] and h["selling_rate"] else "-",
                            "jt30": calc_30jt(h) if h["buying_rate"] and h["selling_rate"] else "-"
                        }
                        for h in history[-1441:]
                    ],
                    "usd_idr_history": usd_idr_history
                }
                await websocket.send_text(json.dumps(msg))
            else:
                await websocket.send_text(json.dumps({"ping": True}))
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(websocket)
