// Analytics with persistent Gist storage
// Gist ID: 11eafa0e67af499db9fe3c79f3595ef3

const GIST_ID = '11eafa0e67af499db9fe3c79f3595ef3';
// Token is read from Vercel env var GIST_TOKEN (set via vercel env add)

async function readCounter() {
    try {
        const res = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
            headers: {
                'Accept': 'application/vnd.github.v3+json',
                'Authorization': `token ${process.env.GIST_TOKEN || ''}`,
                'User-Agent': 'Vercel-Analytics'
            },
            signal: AbortSignal.timeout(5000)
        });
        if (!res.ok) return null;
        const gist = await res.json();
        const raw = gist.files['counter.json'].content;
        return JSON.parse(raw);
    } catch (e) {
        console.error('readCounter error:', e.message);
        return null;
    }
}

async function writeCounter(counter) {
    try {
        const res = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
            method: 'PATCH',
            headers: {
                'Accept': 'application/vnd.github.v3+json',
                'Authorization': `token ${process.env.GIST_TOKEN || ''}`,
                'Content-Type': 'application/json',
                'User-Agent': 'Vercel-Analytics'
            },
            body: JSON.stringify({
                files: {
                    'counter.json': {
                        content: JSON.stringify(counter, null, 2)
                    }
                }
            }),
            signal: AbortSignal.timeout(5000)
        });
        return res.ok;
    } catch (e) {
        console.error('writeCounter error:', e.message);
        return false;
    }
}

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') return res.status(200).end();

    // Also keep in-memory cache for speed
    if (!global._visitorCount) global._visitorCount = 0;
    if (!global._lastVisits) global._lastVisits = [];
    if (!global._pageCounts) global._pageCounts = {};

    if (req.method === 'GET') {
        // Try to get persistent counter, fall back to memory
        const persistent = await readCounter();
        const total = persistent ? persistent.total : global._visitorCount;
        const pages = persistent ? persistent.pages : global._pageCounts;

        return res.json({
            visitors: total,
            pages: pages,
            lastVisits: global._lastVisits.slice(0, 20),
            persisted: !!persistent
        });
    }

    if (req.method === 'POST') {
        let body = {};
        try {
            if (typeof req.body === 'string') body = JSON.parse(req.body);
            else if (req.body) body = req.body;
        } catch (e) {}

        const page = body.page || 'unknown';

        // Update in-memory
        global._visitorCount++;
        global._pageCounts[page] = (global._pageCounts[page] || 0) + 1;
        global._lastVisits.unshift({
            time: new Date().toISOString(),
            page: page,
            referrer: body.referrer || 'direct'
        });
        if (global._lastVisits.length > 500) global._lastVisits.pop();

        // Update persistent counter in Gist
        let counter = await readCounter();
        if (!counter) counter = { total: 0, pages: { search: 0, admin: 0 }, lastReset: '' };
        counter.total++;
        counter.pages[page] = (counter.pages[page] || 0) + 1;
        counter.updatedAt = new Date().toISOString();
        await writeCounter(counter);

        return res.json({
            ok: true,
            count: counter.total,
            pages: counter.pages,
            persisted: true
        });
    }

    return res.status(405).json({ error: 'Method not allowed' });
}
