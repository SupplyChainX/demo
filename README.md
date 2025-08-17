# SupplyChainX

 **Intelligent procurement and supply chain resilience platform**

SupplyChainX is an end‑to‑end, multi‑agent, data‑driven platform that predicts, mitigates, and manages global supply‑chain disruption while optimizing shipping routes, procurement decisions, and risk posture.

## Key Features

* **Predictive Risk Sensing**: Weather, geopolitical, and supplier risk monitoring
* **Multi-Carrier Routing**: Sea and air route optimization with real-time alternatives
* **Autonomous Procurement**: AI-powered PO generation and supplier evaluation
* **Human-in-the-Loop Governance**: Policy enforcement with explainable AI decisions
* **Real-time Intelligence**: Live dashboards, maps, and agent recommendations

**Current Scope:** Core multi-carrier routing with live APIs, comprehensive AI agent system, advanced analytics, risk prediction, procurement automation backend and real-time dashboards.

**Implemented Features:**

- Multi-carrier route generation (Maersk, DHL, FedEx)
- AI agent architecture with 5 autonomous agents
- Real-time risk prediction and intelligence
- Route optimization with risk-weighted scoring
- Advanced analytics and ML pipeline setup
- Procurement agent with AI-powered PO generation
- Agent dashboard for monitoring and control
- Comprehensive user interface with real-time updates

### Problem & Impact

The inability of existing supply chain management system to effectively predict and proactively manage disruptions, which results in costly delays, routing and inventory shortage. This lack of real-time predictive insight has led to significant global delay, shortages, and price overruns over the years, particualrly during events like the Suez Canal blockage, where goods were required to be rerouted through the best available alternatives.

**Situation Analysis**
Current supply chain management systems heavily rely on manual interventions, retrospective data, and siloed processes, resulting in delayed responses to crises that can significantly disrupt commerce, elevate costs, and compromise economic stability.

**The solution**
Predictive agents that anticipate disruptions and propose policy‑compliant actions (reroute, reorder, negotiate purchase order) with full explainability and human approvals.

**Business Impact**
Faster decisions, lower risk exposure, improved ETA reliability, and auditable governance without adding operational complexity.

---

### Technology Stack

**Frontend**

* Bootstrap 5.3
* Jinja2
* Chart.js
* Leaflet (OpenStreeMap tiles)

**Backend**

* Python/Flask (modular blueprints)
* Flask-SocketIO for real-time updates

**Database**

* SQLite (development/MVP), WAL mode enabled
* SQLite-Vec extension for local embedding search (384-dim vectors)

**AI/ML**

* IBM watsonx.ai inference
* LangChain + watsonx API
* Granite-3.2-8B-Instruct for planning, drafting and explanations

**Asynchronous IO**

* Redis only (no Kafka, no RabbitMQ)
  * Redis Streams for queues (inte-agent comms)
  * Redis Pub/Sub for UI broadcast

```yaml
Browser <—(Socket.IO)— Flask API/Socket server
                        |  \
                        |   \-- SQLite (OLTP + audit + outbox)
                        |
                   Redis (one instance)
                     ├─ Streams (risk.events, shipments.status, procurement.actions, approvals.requests)
                     └─ Pub/Sub (ui.broadcast)

Background loops inside the same web container:
  - OutboxPublisher: reads SQLite.outbox → XADD to Redis Streams
  - OrchestratorAgent: XREADGROUP on Streams → writes Recommendations/Approvals → PUBLISH ui events
  - Risk/Route/Procurement Agents: same pattern (consume → act → write DB → enqueue next)
  - UIBridge: Redis pub/sub → socketio.emit(...)

```

**Deployment**

* IBM Cloud VM

**Storage**

* IBM Cloud Object Storage (document/contracts/SLA upload)

**Carrier & External Integrations**

Current live integrations:

* Maersk (sea schedules / mock + enrichment) – custom adapter
* DHL Express (air) – via Karrio + custom normalization
* FedEx (air) – via Karrio
* OpenRouteService (road distance estimates & polyline simplification)
* Geospatial utilities (geopy, polyline)

Scaffolded Data adapters:

* UPS (credentials & Karrio module installed; logic to activate deferred)
* Weather, geopolitical, supplier filings (API keys present, adapter methods stubbed for later ingestion)

Security note: Real API secret values should NOT be committed. See “Secrets & Environment”.

---

* Basemaps & routing: OpenStreetMap (tiles), OpenRouteService/OSRM for road routing (demo/self‑host)
* Maritime: AIS (free feeds), NOAA CO‑OPS/PORTS, NDBC buoys
* Aviation: OpenSky (non‑commercial), FAA Aviation Weather (METAR/TAF/SIGMET)
* Weather/Ocean: NOAA NOMADS (GFS/waves), Open‑Meteo (non‑commercial)
* Road incidents: 511/WZDx feeds (where available)
* Geopolitics/News: GDELT (event/news signals)
* Supplier exposure (open data): OpenCorporates / SEC EDGAR / Companies House / SEDAR+ (registries & filings)
* Notififications
  * SMS
    * Twilio
  * Email
    * SendGrid
    * Flask-Mail

NOTE: Commercial carriers and APIs such as `D&B` are explicitely excluded; But can be easily added to the settings interface later as optional integration.

---

### Prerequisites

**System Requirements:**

- Python 3.9+
- Redis 6.0+
- SQLite 3.35+ (WAL support)
- Node.js 16+ (for frontend tooling)

**Development Tools:**

- Git
- VS Code
- Postman (API testing)

**Required Services:**

- IBM watsonx.ai account with API access
- Redis server (local or cloud)
- IBM Cloud Object Storage bucket

### Running the Application

#### 1. Local (Python)

```
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env  # create (see below to build example)
python init_db.py     # or scripts/create_demo_user.py etc.
python run.py
```

Visit: http://localhost:5001

### Environment & Secrets

The repository currently contains a `.env` file with real-looking API keys. For security you should:

1. Remove/rename committed secret file & add to `.gitignore`.
2. Rotate any exposed keys immediately.
3. Provide a sanitized `.env.example` like:

```
FLASK_ENV=development
SECRET_KEY=change_me
SQLALCHEMY_DATABASE_URI=sqlite:///supplychainx.db
IBM_COS_API_KEY=your_key
WATSONX_APIKEY=your_key
FEDEX_API_KEY=your_key
FEDEX_SECRET=your_secret
DHL_API_KEY=your_key
DHL_API_SECRET=your_secret
MAERSK_API_KEY=your_key
OPENROUTESERVICE_API_KEY=your_key
MAPBOX_API_KEY=your_key
REDIS_URL=redis://localhost:6379/0
```

---

### Contributing

Open an issue describing enhancement or bug. Include reproduction steps & environment. Use feature branches + PR with test updates.

### API Documentation

Once running, access:

- Swagger UI: http://localhost:5001/api/docs
- WebSocket Events: See `/docs/websocket-events.md`
- Agent APIs: See `/docs/agent-apis.md`

---