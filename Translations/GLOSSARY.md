# Glossario italiano per boxes.py / LaserBox

Contesto: boxes.py genera i disegni di taglio per scatole e oggetti da tagliare al laser
(compensato, MDF, plexiglass). Il pubblico è il maker italiano: registro tecnico ma semplice,
dare del "tu" non serve perché i testi sono descrittivi; usare forme impersonali o l'infinito
("imposta", "usa" vanno bene nei consigli rivolti all'utente — preferire la 2ª persona singolare).

## Regole generali

- Mai tradurre parola per parola: rendere il senso come lo scriverebbe un maker italiano.
- Conservare esattamente: segnaposto (`%s`, `%d`, `{name}`, `{0}`), link e URL Markdown
  (`[🛈](https://…)`, `![…](static/…)`), sintassi Markdown (titoli `#`, elenchi `*`/`-`, `**`,
  backtick), sequenze `\n`, nomi di parametri citati nel testo (es. "--sx", "sx", "h", "FingerJoint_play"),
  lettere dei tipi di bordo (e, E, f, F, h, …), unità (mm), nomi di prodotti e marchi
  (NEMA, DIN, Gridfinity, Agricola, IKEA, Raspberry Pi, Arduino, Ponoko…).
- Le **sigle dei parametri** brevi (x, y, h, hi, sx, sy, sh, d, r, n…) restano uguali (msgstr = msgid).
  L'app però non le mostra: `PARAMETER_NAMES` in `LaserBox/bridge.py` le sostituisce con un nome
  (in base al testo d'aiuto, perché "h" non è sempre l'altezza) tradotto con `msgctxt "parameter"`.
- I **nomi dei parametri** descrittivi (top_edge, bottom_lip, grip_percentage…) si traducono in
  un'etichetta italiana breve, minuscola, senza underscore: "bordo superiore", "labbro inferiore",
  "percentuale di presa". Massimo 3–4 parole.
- I **nomi dei generatori** (UniversalBox, TypeTray…) diventano un nome italiano naturale con
  maiuscola iniziale solo sulla prima parola: "Scatola universale", "Vassoio con scomparti".
  Se il nome è un marchio o un nome proprio (Agricola, Gridfinity, Rack19Box) mantenerlo, al massimo
  aggiungendo il tipo: "Inserto per Agricola", "Box rack 19\"".
- Le **scelte** (rectangular, springs, flat…) sono etichette: tradurle brevi e minuscole.
- Testi di aiuto: frase minuscola senza punto finale (come l'originale), "(in mm)" resta, "(multiples of
  thickness)" → "(multipli dello spessore)".
- Numeri decimali nei testi: lasciare il punto se fanno parte di un esempio di valore da digitare
  (es. "0.5"), perché il campo accetta il punto.
- Correggere in silenzio gli evidenti refusi dell'originale ("he lids" → "i coperchi").
- Se `msgid` è già universale (sigla, lettera, numero, sola URL) metti `msgstr` uguale a `msgid`.

## Termini

| Inglese | Italiano |
|---|---|
| box | scatola |
| crate | cassetta |
| case / enclosure | contenitore / custodia |
| tray | vassoio |
| drawer | cassetto |
| drawer insert / divider tray | divisorio per cassetti |
| shelf / shelves | mensola / ripiano / scaffale (secondo contesto) |
| rack | rack (elettronica) / portaoggetti, rastrelliera (altri casi) |
| wall (of a box) | parete |
| inner wall / divider | parete interna / divisorio |
| bottom / floor | fondo |
| top | parte superiore (se è il pezzo: "coperchio" solo se lo è davvero) |
| side | lato / fianco |
| front / back | fronte (parte anteriore) / retro (parte posteriore) |
| lid | coperchio |
| slide-on lid | coperchio scorrevole |
| click-on lid | coperchio a scatto |
| hinge | cerniera |
| hinge pin | perno della cerniera |
| cabinet hinge | cerniera da anta |
| chest hinge | cerniera da baule |
| living hinge / flex | cerniera flessibile / taglio flessibile (il motivo di tagli che rende piegabile il legno) |
| edge (type of edge) | bordo (tipo di bordo) |
| straight edge | bordo dritto |
| outset | sporgente / sporgenza |
| finger joint | incastro a pettine |
| finger (of a finger joint) | dente |
| space (between fingers) | spazio (tra i denti) |
| finger holes | asole (per i denti) |
| finger hole edge | bordo con asole |
| play | gioco |
| burn / burn correction | compensazione del taglio (kerf) — come etichetta del parametro "burn": "compensazione kerf" |
| kerf | kerf (larghezza del taglio) |
| thickness (of the material) | spessore (del materiale) |
| outside (measurements) | misure esterne |
| inner / inside | interno |
| tabs (micro-joints holding parts in the sheet) | ponticelli |
| spacing (between parts on the sheet) | distanza tra i pezzi |
| labels | etichette |
| reference (rectangle) | riferimento (rettangolo di riferimento per verificare la scala) |
| inner corners: loop / corner / backarc | angoli interni: occhiello / angolo vivo / arco inverso |
| dogbone | dogbone (osso di cane) |
| section(s) (sx, sy, sh) | scomparto/i (sezioni lungo x, y, h) |
| compartment | scomparto |
| stackable | impilabile |
| feet | piedini |
| dovetail | coda di rondine |
| grip / handle | presa / maniglia |
| handle hole | foro maniglia |
| knob | pomello |
| hook | gancio |
| peg / pin | piolo / perno |
| screw / bolt / nut | vite / bullone / dado |
| mounting holes | fori di fissaggio |
| wall mounted | da parete |
| French cleat | listello alla francese (French cleat) |
| slot | fessura / scanalatura |
| notch | tacca |
| groove | scanalatura |
| brim | bordo rialzato (del coperchio) |
| fang (flatfang lid) | dente di aggancio |
| lip | labbro / battuta |
| gear / pulley / belt | ingranaggio / puleggia / cinghia |
| tooth / teeth | dente / denti |
| bearing | cuscinetto |
| stepper motor | motore passo-passo |
| burn test | test di taglio |
| sample | campione / esempio |
| part | pezzo |
| layout | disposizione / layout |
| pattern | motivo / schema |
| hole pattern | motivo di fori |
| hex holes | fori esagonali |
| clearance | spazio libero / tolleranza |
| tolerance | tolleranza |
| radius / diameter | raggio / diametro |
| depth / width / height / length | profondità / larghezza / altezza / lunghezza |
| angle | angolo |
| card (playing cards) | carte da gioco |
| board game insert | inserto per gioco da tavolo |
| unstable (generators) | sperimentali |
| Settings for X | Impostazioni X (es. "Settings for Finger Joints" → "Impostazioni incastri a pettine") |
| Default Settings | Impostazioni generali |
| <Generator> Settings | Impostazioni <nome tradotto del generatore> |

## Gruppi

Boxes → Scatole · Boxes with flex → Scatole con cerniera flessibile · Trays and Drawer Inserts →
Vassoi e divisori per cassetti · Shelves → Mensole e scaffali · WallMounted → Da parete ·
Hole patterns → Motivi di fori · Parts and Samples → Pezzi e campioni · Misc → Varie ·
Unstable → Sperimentali
