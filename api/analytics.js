export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') return res.status(200).end();

    if (req.method === 'GET') {
        return res.json({ visitors: global._visitorCount || 0, lastVisits: global._lastVisits || [] });
    }

    if (req.method === 'POST') {
        try {
            let body = req.body;
            // Vercel may auto-parse or leave as string
            if (typeof body === 'string') body = JSON.parse(body);
            if (!body) body = {};

            if (!global._visitorCount) global._visitorCount = 0;
            if (!global._lastVisits) global._lastVisits = [];

            global._visitorCount++;

            const visit = {
                time: new Date().toISOString(),
                page: body.page || 'unknown',
                referrer: body.referrer || 'direct',
                ua: (req.headers['user-agent'] || '').substring(0, 100)
            };

            global._lastVisits.unshift(visit);
            if (global._lastVisits.length > 500) global._lastVisits.pop();

            return res.json({ ok: true, count: global._visitorCount });
        } catch (e) {
            return res.status(400).json({ error: 'Invalid request' });
        }
    }

    return res.status(405).json({ error: 'Method not allowed' });
}
