// Vercel serverless analytics — stores in global memory
// Survives across warm invocations; resets on cold start
// Use Vercel KV for persistence if available

export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') return res.status(200).end();

    // Init globals
    if (!global._visitorCount) global._visitorCount = 0;
    if (!global._lastVisits) global._lastVisits = [];
    if (!global._pageCounts) global._pageCounts = {};
    if (!global._uniqueIPs) global._uniqueIPs = new Set();

    if (req.method === 'GET') {
        return res.json({
            visitors: global._visitorCount,
            uniqueIPs: global._uniqueIPs.size,
            pages: global._pageCounts,
            lastVisits: global._lastVisits.slice(0, 20)
        });
    }

    if (req.method === 'POST') {
        let body = {};
        try {
            if (typeof req.body === 'string') body = JSON.parse(req.body);
            else if (req.body) body = req.body;
        } catch (e) {}

        global._visitorCount++;

        const ip = req.headers['x-forwarded-for'] || req.headers['x-real-ip'] || 'unknown';
        global._uniqueIPs.add(ip);

        const page = body.page || 'unknown';
        global._pageCounts[page] = (global._pageCounts[page] || 0) + 1;

        const visit = {
            time: new Date().toISOString(),
            page: page,
            referrer: body.referrer || 'direct',
            ip: ip.toString().substring(0, 30)
        };

        global._lastVisits.unshift(visit);
        if (global._lastVisits.length > 500) global._lastVisits.pop();

        return res.json({
            ok: true,
            count: global._visitorCount,
            uniqueIPs: global._uniqueIPs.size,
            pages: global._pageCounts
        });
    }

    return res.status(405).json({ error: 'Method not allowed' });
}
