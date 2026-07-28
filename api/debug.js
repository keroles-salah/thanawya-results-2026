export default async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') return res.status(200).end();

    const TOKEN = process.env.GIST_TOKEN || '';
    return res.json({
        hasToken: !!TOKEN,
        tokenLength: TOKEN.length,
        tokenPreview: TOKEN.substring(0, 8) + '...'
    });
}
