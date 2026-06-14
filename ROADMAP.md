# Roadmap

Planned analyzer enhancements — verifiable checks that aren't yet implemented.

## Crystal / Oscillator

- [x] **XL-001**: Verify crystal load capacitance — compute `C_load = (C1×C2)/(C1+C2) - C_stray` from the two load caps and compare against crystal datasheet spec. Flag mismatch (common source of clock drift/no-start).

## Pull-up / Pull-down Verification

- [x] **PU-001**: I2C buses (SDA/SCL) must have pull-ups. Flag if missing.
- [ ] **PU-002**: SPI chip-select lines should have pull-ups (idle-high). Flag directly-driven CS with no pull-up — risks bus contention during MCU reset.
- [ ] **PU-003**: Reset/enable lines need pull-up with RC time constant. Flag floating reset inputs on ICs.
- [ ] **PU-004**: UART TX lines should idle high (pull-up or driven). Flag floating TX.

## Antenna Keepout (PCB)

- [x] **AK-001**: WiFi/BLE modules (ESP32-WROOM, ESP32-S3-WROOM, nRF52 modules) require a ground-free zone around the antenna region. Flag copper pours, traces, or components intruding into the antenna keepout area.

## USB Signal Integrity

- [ ] **USB-001**: D+/D- differential pair length matching — flag if mismatch exceeds 2mm.
- [ ] **USB-002**: USB 2.0 series resistors (22Ω typical on D+/D-) — flag if missing.
- [ ] **USB-003**: D+/D- trace width/spacing vs stackup for 90Ω differential impedance.

## Decoupling Placement (PCB)

- [ ] **DP-001**: Verify bypass cap placement distance — each IC's 100nF cap should be within 3mm of its power pin. Flag caps placed far from their IC.

## ESD Protection Completeness

- [ ] **ESD-001**: Promote EP-AUD to warning when external connector pins reach a microcontroller without TVS/ESD protection on the path.

## Boot Configuration

- [x] **BOOT-001**: ESP32 bootstrap pins (GPIO0, GPIO2, GPIO12, GPIO45, GPIO46 for S3) connected to peripherals that may drive during reset — flag potential boot-mode conflicts.
- [ ] **BOOT-002**: STM32 BOOT0/BOOT1 pin state verification.

## Power Sequencing

- [ ] **SEQ-001**: Detect ICs with known sequencing requirements (VCORE before VIO) and verify the enable/PG chain doesn't violate ordering.

## Floating / Mis-connected Pins

- [ ] **FP-001**: IC input pins left floating (no pull-up/down, no driver) — flag based on pin electrical type.
- [ ] **FP-002**: NC (no-connect) pins accidentally connected to a net.

## Thermal Pad Connectivity

- [ ] **TP-001**: QFN/DFN exposed pad net assignment — verify EP connects to GND (or datasheet-specified net), not left unconnected.
