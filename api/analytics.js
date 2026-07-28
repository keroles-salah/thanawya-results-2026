// Analytics backed by Firebase Realtime Database
// Write uses server secret (secure), read is public (rules: read=true, write=false)
// Tracking is done server-side via Vercel function (not from browser)

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') return res.status(200).end();

    const DB = 'https://f-o-x-284eb-default-rtdb.firebaseio.com';
    const SECRET = process.env.FIREBASE_SECRET || '';

    async function readCounter() {
        try {
            const r = await fetch(`${DB}/analytics.json`, { signal: AbortSignal.timeout(5000) });
            if (!r.ok) return null;
            const d = await r.json();
            return d || { total: 0, pages: {}, lastVisits: [] };
        } catch (e) { return null; }
    }

    async function writeCounter(counter) {
        if (!SECRET) {
            // Fallback: try without auth (will fail if rules don't allow write)
            const r = await fetch(`${DB}/analytics.json`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(counter),
                signal: AbortSignal.timeout(5000)
            });
            return r.ok;
        }
        const r = await fetch(`${DB}/analytics.json?auth=${SECRET}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(counter),
            signal: AbortSignal.timeout(5000)
        });
        return r.ok;
    }

    if (req.method === 'GET') {
        const counter = await readCounter();
        return res.json({
            visitors: counter ? counter.total : 0,
            pages: counter ? (counter.pages || {}) : {},
            lastVisits: (counter && counter.lastVisits) ? counter.lastVisits.slice(-20) : [],
            backed: 'firebase'
        });
    }

    if (req.method === 'POST') {
        let body = {};
        try {
            if (typeof req.body === 'string') body = JSON.parse(req.body);
            else if (req.body) body = req.body;
        } catch (e) {}

        const page = body.page || 'unknown';

        // Read current counter from Firebase
        let counter = await readCounter();
        if (!counter || !counter.total && counter.total !== 0) {
            counter = { total: 0, pages: {}, lastVisits: [] };
        }

        counter.total++;
        counter.pages[page] = (counter.pages[page] || 0) + 1;

        const visit = {
            time: new Date().toISOString(),
            page: page,
            ref: body.referrer || 'direct'
        };
        if (!counter.lastVisits) counter.lastVisits = [];
        counter.lastVisits.push(visit);
        if (counter.lastVisits.length > 100) counter.lastVisits = counter.lastVisits.slice(-100);

        counter.updatedAt = new Date().toISOString();

        const written = await writeCounter(counter);

        return res.json({
            ok: true,
            count: counter.total,
            pages: counter.pages,
            persisted: written
        });
    }

    return res.status(405).json({ error: 'Method not allowed' });
}
