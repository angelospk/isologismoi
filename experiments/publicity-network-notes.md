# Έλεγχος δημόσιων requests ΓΕΜΗ — 2026-10-04

Το browser βρίσκει το ΓΕΜΗ **194123801000**, STRIDE Ι.Κ.Ε. Δεν επαληθεύτηκε μόνιμη αναπαραγωγή με απλό HTTP ή headless browser.

## Μετρημένα

| Δοκιμή | Αποτέλεσμα |
|---|---|
| T3 collaborative browser: αναζήτηση ΓΕΜΗ | STRIDE Ι.Κ.Ε., ενεργή |
| Αναζήτηση | `POST /api/search`, καταγράφηκε στο resource timing. Το body δεν καταγράφηκε |
| Autocomplete | `/api/autocomplete/194123801000`, resource timing· το method δεν καταγράφηκε απευθείας |
| Άνοιγμα προφίλ | `POST /api/company/details`, **200**, body keys `query, token, language`, response key `companyInfo` |
| Απλό HTTP από mini PC | ίδιο endpoint, `{"query":"194123801000","language":"el","token":""}` → **400**, `{"error":"Bad request"}` |
| Κανονικό Chrome headless από mini PC | άνοιγμα `/company/194123801000` → DOM **429 Too Many Requests**, nginx. Η δοκιμή σταμάτησε |

Τα μόνα JavaScript-readable cookie names που παρατηρήθηκαν: `_ga_L7TS87DDSM`, `_ga`, `next-i18next`. Δεν καταγράφηκαν τιμές. Αυτό **δεν** αποδεικνύει απουσία HttpOnly cookies ή cookies τρίτων.

Το φορτωμένο επίσημο bundle `/_next/static/chunks/pages/company/%5BarGEMI%5D-44b20ba8e2dea415.js` δείχνει reCAPTCHA action `companyDetailsLoad` πριν από το POST. Ο κώδικας στέλνει `{query:w,token:e,language:B}` και χρησιμοποιεί `companyInfo.payload`. Δεν μεταφέρθηκε token από browser σε HTTP. Η ακριβής δομή του `w` δεν επιβεβαιώθηκε ανεξάρτητα. Συνεπώς το **400 δεν αποδεικνύει μόνο του ότι απαιτείται token**· μπορεί να είναι και σφάλμα σχήματος body. Ο συνδυασμός bundle/reCAPTCHA/429 δείχνει πάντως ότι ένα μόνιμο απλό replay δεν είναι τεκμηριωμένο.

## Κρίση

Η δημόσια ιστοσελίδα έχει άλλο interface από το συμβατικό OpenData Swagger. Αυτό δεν δίνει δικαίωμα ή εγγύηση για crawler εκτός του ορίου 8 req/min. Δεν εφαρμόστηκε stealth, αλλαγή IP, επίλυση CAPTCHA ή rotation cookies. Δεν έγινε μαζική λήψη.

Ένα cookie που δουλεύει τώρα δεν είναι σταθερό API συμβόλαιο. Token/session μπορεί να λήξει, το bundle να αλλάξει και το anti-bot να διαφέρει ανά IP. Για μόνιμη υπηρεσία προτείνεται το επίσημο OpenData API, ο υπάρχων κοινός limiter και γραπτή συμφωνία για bulk χρήση. Η ιστοσελίδα είναι χρήσιμη για μικρούς χειροκίνητους ελέγχους.

## Ανάθεση OpenCode

Δύο app-owned sub-agent attempts απέτυχαν πριν εκτελέσουν δουλειά:
1. `openai/gpt-6.1-sol`: provider 401.
2. `opencode/mimo-v2.6-flash-free`: provider rate limit.

Τα παραπάνω πειράματα τα εκτέλεσε ο κύριος agent. Δεν παρουσιάζονται ως αποτέλεσμα του OpenCode. Τα αρχεία `publicity-evidence/*.json` περιέχουν την αποθηκευμένη τεκμηρίωση.

