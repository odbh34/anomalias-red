/*
 * main.cpp – Firmware ESP32 para detección de anomalías DNS
 * usando TinyML y NAPT.
 *
 * Flujo:
 *   1. Escucha consultas DNS entrantes (puerto 53 UDP)
 *   2. Acumula estadísticas en ventanas de 3s
 *   3. Extrae features: cantidad, únicos, nuevos dominios
 *   4. Clasifica con árbol de decisión TinyML (modelo.h)
 *   5. Envía resultado vía POST a servidor EC2 cada ~10s
 *   6. Comparte internet (NAPT) entre STA y AP
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WiFiClient.h>
#include <lwip/lwip_napt.h>
#include "config.h"
#include "modelo.h"

// -----------------------------------------------------------
// Variables globales de ventana y estadísticas
// -----------------------------------------------------------
static WiFiUDP dns_server;            // Servidor DNS UDP local
static volatile char current_label[16] = "unlabeled"; // Etiqueta manual desde Serial
static uint32_t window_qty = 0;      // Consultas DNS en ventana actual
static uint32_t window_unique = 0;   // Dominios distintos en ventana
static uint32_t window_new = 0;      // Dominios nunca antes vistos
static uint32_t window_start = 0;    // Timestamp inicio de ventana
static uint32_t total_dns_queries = 0; // Total acumulado
static uint32_t total_dns_responses = 0;
static uint32_t last_status_print = 0;
static uint32_t last_post_time = 0;  // Control de rate para POST
static int last_pred = 0;            // Última predicción enviada
static float last_anom = 0;
static uint32_t last_qty = 0, last_unique = 0, last_new = 0;

// Diccionario global de dominios vistos (evita saturación)
#define MAX_DOMAINS 512
static char all_domains[MAX_DOMAINS][48];
static uint32_t n_all = 0;

// Dominios vistos en la ventana actual
#define MAX_WIN_DOMAINS 64
static char win_domains[MAX_WIN_DOMAINS][48];
static uint32_t n_win = 0;

// -----------------------------------------------------------
// Detección de anomalías (algoritmo de Welford online)
// Calcula media y varianza incrementalmente sin almacenar
// el historial completo. El score es la suma de desviaciones
// normalizadas (z-score) de las 3 features.
// -----------------------------------------------------------
#define N_FEAT 3
struct AnomalyStats { uint32_t count; double mean[N_FEAT]; double m2[N_FEAT]; };
static AnomalyStats anomaly;
static uint32_t anomaly_ready = 0;

void reset_anomaly() {
    anomaly.count = 0;
    for (int i = 0; i < N_FEAT; i++) { anomaly.mean[i] = 0; anomaly.m2[i] = 0; }
    anomaly_ready = 0;
    n_all = 0;
    Serial.println("[A] Reset");
}

static void update_anomaly(double vals[N_FEAT]) {
    anomaly.count++;
    for (int i = 0; i < N_FEAT; i++) {
        double d = vals[i] - anomaly.mean[i];
        anomaly.mean[i] += d / anomaly.count;
        anomaly.m2[i] += d * (vals[i] - anomaly.mean[i]);
    }
}

static float anomaly_score(double vals[N_FEAT]) {
    if (anomaly.count < 2) return 0;
    double s = 0;
    for (int i = 0; i < N_FEAT; i++) {
        double var = anomaly.m2[i] / (anomaly.count - 1);
        double sd = sqrt(var);
        if (sd > 0.01) s += fabs(vals[i] - anomaly.mean[i]) / sd;
    }
    return (float)s;
}

// -----------------------------------------------------------
// Funciones auxiliares para dominio
// domain_eq: comparación segura de strings de hasta 48 chars
// is_new: true si el dominio nunca se había visto globalmente
// add_global: agrega al diccionario global (max 512)
// in_win: true si ya apareció en la ventana actual
// add_win: agrega al conjunto de la ventana (max 64)
// -----------------------------------------------------------
static bool domain_eq(const char *a, const char *b) {
    for (int i = 0; i < 48; i++) { if (a[i] != b[i]) return false; if (a[i] == 0) return true; }
    return true;
}
static bool is_new(const char *d) {
    for (uint32_t i = 0; i < n_all; i++) if (domain_eq(all_domains[i], d)) return false;
    return true;
}
static void add_global(const char *d) {
    if (n_all < MAX_DOMAINS) { strncpy(all_domains[n_all], d, 47); all_domains[n_all][47] = 0; n_all++; }
}
static bool in_win(const char *d) {
    for (uint32_t i = 0; i < n_win; i++) if (domain_eq(win_domains[i], d)) return true;
    return false;
}
static void add_win(const char *d) {
    if (n_win < MAX_WIN_DOMAINS) { strncpy(win_domains[n_win], d, 47); win_domains[n_win][47] = 0; n_win++; }
}

// -----------------------------------------------------------
// Parser de nombres DNS (formato de etiquetas con
// compresión de punteros RFC 1035). Extrae el dominio
// consultado desde un paquete DNS raw.
// -----------------------------------------------------------
uint8_t dns_buf[512];

static const uint8_t *parse_name(const uint8_t *p, const uint8_t *end, const uint8_t *msg, char *out) {
    size_t o = 0;
    while (p < end) {
        uint8_t l = *p;
        if (l == 0) { p++; break; }
        if (l & 0xC0) {
            uint16_t off = ((p[0] & 0x3F) << 8) | p[1];
            p += 2;
            if (off >= (uint16_t)(end - msg)) return NULL;
            return parse_name(msg + off, end, msg, out + o);
        }
        p++;
        if (p + l > end) return NULL;
        if (o > 0 && o < 63) out[o++] = '.';
        for (uint8_t i = 0; i < l && o < 63; i++) out[o++] = *p++;
    }
    out[o] = 0;
    return p;
}

// -----------------------------------------------------------
// Manejador de consultas DNS entrantes
// 1. Lee paquete UDP del cliente
// 2. Ignora respuestas (bit QR)
// 3. Extrae el nombre de dominio consultado
// 4. Actualiza contadores de la ventana
// 5. Reenvía la consulta a Google DNS (8.8.8.8:53)
//    y retransmite la respuesta al cliente original
// -----------------------------------------------------------
void handle_dns() {
    int sz = dns_server.parsePacket();
    if (!sz) return;

    int len = dns_server.read(dns_buf, sizeof(dns_buf));
    if (len < 12) return;
    if (dns_buf[2] & 0x80) return; // skip responses

    char domain[64];
    const uint8_t *p = parse_name(dns_buf + 12, dns_buf + len, dns_buf, domain);
    if (!p || domain[0] == 0) return;

    // Count
    window_qty++;
    total_dns_queries++;
    if (!in_win(domain)) {
        window_unique++;
        add_win(domain);
        if (is_new(domain)) {
            window_new++;
            add_global(domain);
        }
    }

    // Forward to 8.8.8.8
    WiFiUDP fwd;
    if (fwd.beginPacket(IPAddress(8, 8, 8, 8), 53)) {
        fwd.write(dns_buf, len);
        fwd.endPacket();
        unsigned long deadline = millis() + 3000;
        while (millis() < deadline) {
            int rlen = fwd.parsePacket();
            if (rlen) {
                uint8_t rbuf[512];
                int rb = fwd.read(rbuf, sizeof(rbuf));
                if (rb > 0) {
                    dns_server.beginPacket(dns_server.remoteIP(), dns_server.remotePort());
                    dns_server.write(rbuf, rb);
                    dns_server.endPacket();
                    total_dns_responses++;
                }
                break;
            }
        }
    }
    fwd.stop();
}

// -----------------------------------------------------------
// Envío HTTP POST al servidor EC2 (csi_ws.py :3002)
// Envía JSON con features, score de anomalía y predicción
// Limitado a 1 POST cada 10 segundos para no saturar.
// -----------------------------------------------------------
static void send_to_server() {
    if (millis() - last_post_time < 10000) return;
    last_post_time = millis();
    WiFiClient c;
    if (!c.connect("18.116.200.170", 3002)) return;
    char buf[256];
    int n = snprintf(buf, sizeof(buf),
        "{\"dns_qty\":%lu,\"dns_unique\":%lu,\"dns_new\":%lu,\"anom\":%.1f,\"pred\":%d,\"label\":\"%s\"}",
        last_qty, last_unique, last_new, last_anom, last_pred, (const char*)current_label);
    char req[512];
    snprintf(req, sizeof(req),
        "POST / HTTP/1.1\r\nHost: 18.116.200.170:3002\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s",
        n, buf);
    c.print(req);
    while (c.available()) c.read();
    c.stop();
}

// -----------------------------------------------------------
// Cierre de ventana: cada DNS_WINDOW_MS (3s) se procesan
// las estadísticas acumuladas:
//   1. Score de anomalía (Welford)
//   2. Clasificación con TinyML (árbol de decisión)
//   3. Impresión por Serial y POST al servidor
// -----------------------------------------------------------
void flush_window() {
    if (window_qty == 0) {
        window_start = millis();
        n_win = 0;
        return;
    }

    double vals[N_FEAT] = {(double)window_qty, (double)window_unique, (double)window_new};
    float asc = anomaly_score(vals);
    bool is_a = (anomaly_ready >= ANOMALY_WARMUP && asc > ANOMALY_THRESHOLD);
    update_anomaly(vals);
    anomaly_ready++;

    // Features escaladas ×100 (el árbol fue entrenado con enteros)
    int32_t f[N_FEAT] = {(int32_t)(window_qty * 100), (int32_t)(window_unique * 100), (int32_t)(window_new * 100)};
    int pred = predecir(f);
    static const char *pred_names[] = {"bg", "fg", "sos"};

    last_qty = window_qty;
    last_unique = window_unique;
    last_new = window_new;
    last_anom = asc;
    last_pred = pred;

    Serial.printf("[W] dns_qty=%d unique=%d new=%d anom=%.1f%s label=%s pred=%s\n",
        window_qty, window_unique, window_new, asc, is_a ? " !!!" : "",
        (const char*)current_label, pred_names[pred]);

    window_qty = 0;
    window_unique = 0;
    window_new = 0;
    n_win = 0;
    window_start = millis();
    send_to_server();
}

// -----------------------------------------------------------
// Inicialización del ESP32
// Modo AP+STA: crea red WiFi local y se conecta a internet.
// Habilita NAPT para compartir internet entre STA y AP.
// Inicia servidor DNS en puerto 53.
// -----------------------------------------------------------
void setup() {
    Serial.begin(115200); delay(500);
    Serial.println("\n=== ESP32 DNS Anomaly (NAPT) ===");
    Serial.println("b=bg  f=fg  s=sospechoso  u=unlabeled  r=reset");

    WiFi.mode(WIFI_AP_STA);
    WiFi.softAP(AP_SSID, AP_PASSWORD);
    Serial.printf("AP: %s  IP: %s\n", AP_SSID, WiFi.softAPIP().toString().c_str());

    WiFi.begin(STA_SSID, STA_PASSWORD);
    Serial.printf("Conectando a %s", STA_SSID);
    for (int i = 0; i < 30 && WiFi.status() != WL_CONNECTED; i++) {
        delay(1000); Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("STA OK: %s\n", WiFi.localIP().toString().c_str());
        ip_napt_enable((uint32_t)WiFi.softAPIP(), 1);
        Serial.printf("NAPT habilitado en AP %s\n", WiFi.softAPIP().toString().c_str());
    } else {
        Serial.println("STA fallo, sin internet compartido");
    }

    dns_server.begin(53);
    Serial.println("DNS en puerto 53");

    window_start = millis();
    Serial.println("=== Listo ===");
    Serial.println("Conecta tu telefono a ESP32-Monitor");
    Serial.println("(los datos celulares pueden quedar encendidos)");
}

// -----------------------------------------------------------
// Bucle principal
//   - handle_dns: procesa consultas entrantes
//   - flush_window: cierra ventana cada 3s y clasifica
//   - Test de internet cada 60s
//   - Status cada 30s
//   - check_serial: etiquetado manual desde monitor serie
// -----------------------------------------------------------
static void check_serial() {
    if (!Serial.available()) return;
    char c = Serial.read();
    if (c == 'b' || c == 'B') { strncpy((char*)current_label, "background", 16); Serial.println(">> bg"); }
    else if (c == 'f' || c == 'F') { strncpy((char*)current_label, "foreground", 16); Serial.println(">> fg"); }
    else if (c == 's' || c == 'S') { strncpy((char*)current_label, "sospechoso", 16); Serial.println(">> sospechoso"); }
    else if (c == 'u' || c == 'U') { strncpy((char*)current_label, "unlabeled", 16); Serial.println(">> unlabeled"); }
    else if (c == 'r' || c == 'R') { reset_anomaly(); }
}

void loop() {
    handle_dns();

    if (millis() - window_start >= DNS_WINDOW_MS) {
        flush_window();
    }

    // Test internet cada 60s desde el ESP32 (no desde el cliente)
    static uint32_t last_inet_test = 0;
    if (millis() - last_inet_test > 60000 && total_dns_queries > 0) {
        last_inet_test = millis();
        WiFiUDP test;
        if (test.beginPacket(IPAddress(8, 8, 8, 8), 53)) {
            uint8_t probe[] = {0xaa,0xbb,0x01,0x00,0x00,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x03,0x77,0x77,0x77,0x06,0x67,0x6f,0x6f,0x67,0x6c,0x65,0x03,0x63,0x6f,0x6d,0x00,0x00,0x01,0x00,0x01};
            test.write(probe, sizeof(probe));
            test.endPacket();
            unsigned long deadline = millis() + 2000;
            bool ok = false;
            while (millis() < deadline) {
                if (test.parsePacket()) { ok = true; break; }
            }
            Serial.printf("[T] internet=%s (DESDE EL ESP32)\n", ok ? "OK" : "SIN RESPUESTA");
        }
        test.stop();
    }

    // Status cada 30s
    if (millis() - last_status_print > 30000) {
        last_status_print = millis();
        Serial.printf("[S] STA=%s AP=%s dns_q=%lu dns_r=%lu wifi=%d\n",
            WiFi.status() == WL_CONNECTED ? "OK" : "DOWN",
            WiFi.softAPIP().toString().c_str(),
            total_dns_queries, total_dns_responses, WiFi.status());
    }

    check_serial();
    delay(1);
}
