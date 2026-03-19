const fs = require('fs');
const path = require('path');

// Manually load .env since dotenv might not be installed
const envPath = path.resolve(__dirname, '.env');
const envFile = fs.readFileSync(envPath, 'utf-8');
envFile.split('\n').forEach(line => {
  const match = line.match(/^([^=]+)=(.*)$/);
  if (match) {
    process.env[match[1].trim()] = match[2].trim();
  }
});

const stripe = require('stripe')(process.env.STRIPE_SECRET_KEY);

async function createLink() {
  try {
    console.log('Creating Product...');
    const product = await stripe.products.create({
      name: 'VeilPiercer Starter ($197)',
      description: 'One-time access. No seats. Yours forever.',
    });

    console.log('Creating Price...');
    const price = await stripe.prices.create({
      product: product.id,
      unit_amount: 19700, // $197.00
      currency: 'usd',
    });

    console.log('Creating Payment Link...');
    const paymentLink = await stripe.paymentLinks.create({
      line_items: [{ price: price.id, quantity: 1 }],
      after_completion: { type: 'redirect', redirect: { url: 'http://127.0.0.1:3000/access.html' } },
    });

    console.log('\n--- NEW STRIPE LINK ---');
    console.log(paymentLink.url);
    console.log('-----------------------\n');
  } catch (error) {
    console.error('Error creating Stripe link:', error.message);
  }
}

createLink();
