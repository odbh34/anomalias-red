# Detección de Anomalías DNS con TinyML en ESP32

Gateway WiFi con ESP32 que captura consultas DNS, las clasifica en
*background* / *foreground* / *sospechoso* usando un árbol de decisión
TinyML, y envía los resultados a un dashboard WebSocket en AWS EC2.

## Estructura del proyecto

```
Red/
├── src/
│   ├── main.cpp          ← Firmware principal (DNS forwarder + TinyML + POST)
│   ├── modelo.h          ← Árbol de decisión generado por procesar.py
│   └── config.h          ← Credenciales WiFi y constantes
├── EC2/
│   ├── dns.html          ← Dashboard en tiempo real (Chart.js + WebSocket)
│   ├── index.html        ← Menú principal con enlace a dns.html
│   ├── keyAmazon.pem     ← Clave SSH para EC2 (no subir a git)
│   ├── informe.tex       ← Informe completo en LaTeX (Overleaf)
│   ├── generar_graficas.py ← Genera métricas y gráficos para el informe
│   └── graficas/         ← PNGs: árbol, confusión, distribución, etc.
├── capturar.py           ← Script guiado de captura de datos (3 fases)
├── procesar.py           ← Limpia datos, entrena árbol, genera modelo.h
├── dataset.csv           ← 123 ventanas etiquetadas (bg/fg/sos)
├── datos_crudos.txt      ← Datos crudos capturados desde el ESP32
├── informe/              ← Copia de los archivos del informe
├── papers/               ← 5 artículos de referencia (estado del arte)
├── platformio.ini        ← Configuración de PlatformIO (espressif32)
└── cmake/                ← Build auxiliar para objetos lwIP (NAPT fix)
```

## Hardware

| Componente | Especificación |
|---|---|
| ESP32 | ESP-WROOM-32, 240 MHz dual-core, 520 KB SRAM, 4 MB flash |
| Conexión | USB 5V (alimentación) + WiFi 2.4 GHz |
| Circuito | Solo el ESP32 (sin sensores externos) |

## Funcionamiento

1. El ESP32 crea una red WiFi (`ESP32-Monitor`) y se conecta a internet
2. Activa NAPT para compartir internet entre AP y STA
3. Captura consultas DNS entrantes (puerto 53), las reenvía a 8.8.8.8
4. Cada 3 segundos cierra una ventana y extrae 3 features:
   - `dns_qty`: consultas en la ventana
   - `dns_unique`: dominios distintos
   - `dns_new`: dominios nunca antes vistos
5. Clasifica con un árbol de decisión de 13 nodos (64.86% accuracy)
6. Envía los resultados por Serial y vía HTTP POST al servidor EC2

## AWS EC2

```
18.116.200.170
├── Puerto 3001  ← WebSocket broker (csi_ws.py)
├── Puerto 3002  ← HTTP POST receptor (csi_ws.py)
└── Puerto 80    ← Apache2 sirve dns.html e index.html
```

- El ESP32 envía JSON via POST a `http://18.116.200.170:3002`
- `csi_ws.py` recibe el POST y lo retransmite a todos los WebSocket clients
- El dashboard (`http://18.116.200.170/dns.html`) se conecta al WebSocket
  y muestra clasificaciones en tiempo real

## Cómo compilar y flashear

```bash
# Compilar
python -m platformio run --project-dir .

# Flashear (desde VSCode: PlatformIO → Upload)
```

## Captura de datos

```bash
python capturar.py
# Sigue las instrucciones: 3 fases de 5 minutos cada una
# b = background, f = foreground, s = sospechoso
# El resultado se guarda en datos_crudos.txt
```

## Entrenar modelo

```bash
python procesar.py
# Lee datos_crudos.txt → genera dataset.csv → entrena árbol → genera modelo.h
```

## Generar gráficas para el informe

```bash
python EC2/generar_graficas.py
# Salida en EC2/graficas/ (PNGs + metricas.txt)
```

## Informe en LaTeX

El archivo `EC2/informe.tex` contiene el informe completo. Para Overleaf:

1. Crear proyecto, pegar `informe.tex`
2. Subir `graficas/` (7 PNGs)
3. Subir `src/main.cpp` y `src/modelo.h`
4. Compilar con pdflatex

## Papers de referencia

Los 5 artículos del estado del arte están en `papers/`:

- Stacking-based TinyML para detección de ataques (PLOS One 2025)
- ML eficiente para detección de intrusiones en ESP32
- TinyML federado sobre LoRaWAN (IJCRT 2026)
- IDS ligero para IIoT con TinyML + Edge AI (Scientific Reports 2026)
- Detección de intrusiones para cortes 5G con validación leakage-free

## Licencia

Proyecto académico — Ingeniería en Sistemas Computacionales.
