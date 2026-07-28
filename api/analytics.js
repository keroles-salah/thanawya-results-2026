export default function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    if (req.method === 'OPTIONS') return res.status(200).end();

    // Simple path redirect — serve from /api/analytics
    if (req.method === 'GET') {
        return res.json({ visitors: global._visitorCount || 0, lastVisits: global._lastVisits || [] });
    }

    if (req.method === 'POST') {
        try {
            const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
            if (!global._visitorCount) global._visitorCount = 0;
            if (!global._lastVisits) global._lastVisits = [];

            global._visitorCount++;

            const visit = {
                time: new Date().toISOString(),
                page: body.page || 'unknown',
                referrer: body.referrer || 'direct',
                userAgent: req.headers['user-agent'] ? req.headers['user-agent'].substring(0, 100) : 'unknown'
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
