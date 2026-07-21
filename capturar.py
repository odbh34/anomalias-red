#!/usr/bin/env python3
"""
Captura guiada: background + normal + sospechoso.
Envía b/f/s al ESP32, muestra cuenta regresiva, guarda en datos_crudos.txt
"""

import sys, time, threading, serial, serial.tools.list_ports
from datetime import datetime, timedelta

BAUD = 115200
OUTPUT = "datos_crudos.txt"

PHASES = [
    ("background", "b", "NO TOQUES el telefono (pantalla apagada)"),
    ("normal", "f", "Visita sitios NORMALES: Google, YouTube, WhatsApp, Instagram"),
    ("sospechoso", "s", "Visita sitios con trackers / publicidad / sospechosos"),
]

DURACION = 5  # minutos por fase

def list_ports():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No se encontraron puertos seriales.")
        sys.exit(1)
    print("Puertos disponibles:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p.device} - {p.description}")
    return [p.device for p in ports]

def countdown(duration_min, ser, f, stop_event):
    end = datetime.now() + timedelta(minutes=duration_min)
    while datetime.now() < end and not stop_event.is_set():
        remaining = end - datetime.now()
        mins, secs = divmod(int(remaining.total_seconds()), 60)
        print(f"\r  Tiempo restante: {mins:02d}:{secs:02d}  ", end="", flush=True)

        import msvcrt
        if msvcrt.kbhit():
            key = msvcrt.getch().decode("utf-8", errors="replace").lower()
            if key in ("b", "f", "s", "u"):
                ser.write(key.encode())
                log = f">>> COMANDO MANUAL: '{key}'"
                print(f"\n{log}")
                f.write(f"{log}\n")

        for _ in range(10):
            if stop_event.is_set():
                break
            time.sleep(0.1)
    print()

def phase(ser, f, label, cmd, instruction, duration_min, stop_event):
    ts = datetime.now().strftime("%H:%M:%S")
    f.write(f"\n# FASE: {label.upper()} - {ts}\n")
    print(f"\n{'='*60}")
    print(f"FASE: {label.upper()} ({duration_min} min)")
    print(f"Instruccion: {instruction}")
    print(f"{'='*60}")

    ser.write(cmd.encode())
    time.sleep(0.1)
    ser.write(cmd.encode())
    log = f">>> AUTO-COMANDO: '{cmd}' enviado al ESP32 para fase {label}"
    f.write(f"{log}\n")
    print(log)

    countdown(duration_min, ser, f, stop_event)

def reader_thread(ser, f, stop_event):
    buf = ""
    while not stop_event.is_set():
        try:
            n = ser.in_waiting or 1
            data = ser.read(n)
            if data:
                text = data.decode("utf-8", errors="replace")
                buf += text
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")
                    if line:
                        ts = datetime.now().strftime("%H:%M:%S")
                        print(f"\r[{ts}] {line}")
                        f.write(f"[{ts}] {line}\n")
        except Exception as e:
            if not stop_event.is_set():
                print(f"\nError: {e}", file=sys.stderr)
                time.sleep(0.5)

def main():
    ports = list_ports()
    idx = 0
    if len(ports) > 1:
        try:
            inp = input(f"Puerto [0-{len(ports)-1}] (default 0): ")
            if inp.strip():
                idx = int(inp)
        except ValueError:
            idx = 0
    port = ports[idx]

    print(f"\nConectando a {port} a {BAUD} baud...")
    ser = serial.Serial(port, BAUD, timeout=0.1)
    time.sleep(2)

    stop_event = threading.Event()

    with open(OUTPUT, "w", buffering=1) as f:
        f.write(f"# Captura iniciada: {datetime.now()}\n")
        f.write(f"# Duracion por fase: {DURACION} min\n\n")

        reader = threading.Thread(target=reader_thread, args=(ser, f, stop_event), daemon=True)
        reader.start()

        print("\n" + "=" * 60)
        print("CAPTURA DE TRAFICO - Deteccion de anomalias")
        print("=" * 60)
        print(f"Duracion por fase: {DURACION} minutos")
        print("Fases: background -> normal -> sospechoso")
        print()
        input("Presiona Enter para iniciar la captura...")

        try:
            for label, cmd, instruction in PHASES:
                phase(ser, f, label, cmd, instruction, DURACION, stop_event)
                print(f"\n--- Fase {label} completada ---")
                if label != PHASES[-1][0]:
                    input("Presiona Enter para continuar a la siguiente fase...")

            print("\n--- Captura completada ---")

        except KeyboardInterrupt:
            print("\n\nCaptura interrumpida por el usuario.")
        finally:
            stop_event.set()
            ts = datetime.now().strftime("%H:%M:%S")
            f.write(f"\n# Captura finalizada: {ts}\n")
            ser.write(b"u")
            time.sleep(0.1)
            ser.close()

    print(f"\nDatos guardados en: {OUTPUT}")
    print("Hecho.")

if __name__ == "__main__":
    main()
