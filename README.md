# PFE PRO — Production Forecast Engine

**Pianificazione, simulazione e controllo economico della produzione per aziende contoterziste.**

> Strumento browser-based per production manager nel contract manufacturing (cosmesi, farmaceutico, alimentare, chimico, packaging). Configura in 30 minuti, risultati immediati.

---

## Cosa fa

PFE PRO simula il piano di produzione giornaliero di una commessa multi-fase, multi-lotto e multi-referenza, calcolando date di completamento, ritardi, e rendimento economico — tutto dal browser, senza installazione.

### Moduli

| Modulo | Funzione |
|--------|----------|
| **Configura** | Definisci fasi, lotti, referenze, risorse, throughput e tariffe €/pz |
| **Eccezioni** | Pannello unificato per fermi, straordinari, cambi turno, variazioni operatori — per giorno singolo, periodo o permanenti |
| **Forecast** | Date di completamento per fase e referenza, alert ritardi su date tassative |
| **Piano** | Piano giornaliero dettagliato con produzione simulata per fase |
| **Gantt** | Timeline visuale delle lavorazioni |
| **Economics** | Monitor economico: tariffa €/pz per fase, ricavi, ore stimate, €/ora |
| **Consuntivo** | Tracciamento produzione reale (cumulativi) |
| **Dashboard** | Vista multi-commessa aggregata |

---

## Logica di simulazione

Il motore rispetta le **dipendenze tra fasi** in modo rigoroso:

- Ogni fase ha un throughput (pz/h/persona) e risorse assegnate (persone × ore)
- Le fasi dipendenti lavorano solo sulla **scorta disponibile** dalla fase a monte
- Dipendenze multiple: la fase a valle usa il **minimo** tra tutte le fasi da cui dipende
- Esempio tipico: `Astucciatura` dipende da `Dosaggio` e `Lottatura` → lavora solo fino al minore tra dosato e lottato

```
Dosaggio (indipendente)
    ↓
Lottatura (dipende da: Dosaggio)
    ↓
Astucciatura (dipende da: Dosaggio + Lottatura → min dei due)
    ↓
Termatura (dipende da: Astucciatura)
```

La simulazione procede giorno per giorno, rispettando:
- Calendario (lun-sab, domenica off)
- Fermi programmati
- Eccezioni configurate (fermi fase, cambi orario/operatori, straordinari)
- Priorità lotti e sequenza referenze

---

## Sistema eccezioni

Pannello unificato che gestisce qualsiasi variazione con un singolo form:

- **Modalità**: giorno singolo · periodo (da → a) · permanente (da giorno in poi)
- **Scope**: selezione fasi con toggle (tutte, alcune, una)
- **Parametri**: ore/giorno, ore sabato, n. persone — vuoto = invariato
- **Tag automatici**: ⛔ Fermo · 🕐 Cambio orario · 👥 Cambio operatori · ⚡ Straordinario · 📋 Altro
- **Slot collassabili**: riepilogo in una riga, espandi per modificare, elimina con ✕

Esempi coperti:
- Giorno 15, dosaggio fermo → ⛔ Fermo, 1 giorno, solo dosaggio
- Sabato 24 si lavora, 6h, 4 persone astucciatura + 2 dosaggio → 2 eccezioni giorno singolo
- Dal 9 al 14, 9 ore tutti → ⚡ Straordinario, periodo, tutte le fasi
- Da giorno 25, 8 persone astucciatura fino a fine → 📋 Altro, permanente, solo astucciatura

---

## Monitor economico

- **Tariffa complessiva €/pz** sulla commessa e **scomposizione per fase**
- **Ricavo totale** e **ricavo per fase**
- **Ore stimate** dalla simulazione e **€/ora effettivo** per fase
- **Avanzamento economico** con barre di progresso e valore prodotto
- **Verifica coerenza**: alert se la somma tariffe fasi ≠ tariffa complessiva

---

## Export PDF

Report stampabili in formato A4 landscape:
- **Forecast** — riepilogo date, ritardi, tabelle per fase
- **Piano** — piano giornaliero fino a 200 giorni
- **Economics** — breakdown economico completo

---

## Stack tecnico

| Layer | Tecnologia |
|-------|-----------|
| Frontend | React 18, single-file JSX |
| Styling | CSS-in-JS, dark theme |
| Storage | localStorage (persistenza browser) |
| Hosting | Vercel (deploy da V0) |
| Dipendenze esterne | Nessuna |

File unico `pfe-v5-pro.jsx` — nessun build toolchain richiesto. Incolla su V0.dev → preview → deploy.

---

## Target

- **Aziende contoterziste** (10–200 dipendenti) nel manifatturiero
- **Production manager** che pianificano con Excel e necessitano di uno strumento dedicato
- **Settori**: cosmesi, farmaceutico, alimentare, chimico, packaging
- **Gap di mercato**: tra ERP enterprise (SAP, PlanetTogether — decine di migliaia €/anno) e tool generici (Katana, MRPeasy — non pensati per contoterzismo multi-commessa)

---

## Roadmap

- [ ] Sincronizzazione dati multi-dispositivo (backend Supabase/Firebase)
- [ ] Import/export JSON commesse
- [ ] Throughput reale calcolato automaticamente da consuntivo
- [ ] Notifiche alert ritardi
- [ ] Vista mobile ottimizzata
- [ ] Multi-utente con permessi (viewer/editor)
- [ ] Integrazione ERP via API

---

## Licenza

Proprietario. Tutti i diritti riservati.

---

*Built with operational intelligence — by a production controller, for production controllers.*
