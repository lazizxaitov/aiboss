const NUMERIC_CURRENCY_LABELS: Record<string, string> = {
  "643": "RUB",
  "760": "SYP",
  "784": "AED",
  "810": "USD",
  "840": "USD",
  "858": "UYU",
  "860": "UZS",
  "978": "EUR",
};

function normalizeCompactText(value: string) {
  return value.replace(/\u00A0/g, " ").trim();
}

export function normalizeCurrencyLabel(currency: string | null | undefined): string | null {
  if (currency == null) {
    return null;
  }

  const normalized = normalizeCompactText(String(currency));
  if (!normalized) {
    return null;
  }

  if (NUMERIC_CURRENCY_LABELS[normalized]) {
    return NUMERIC_CURRENCY_LABELS[normalized];
  }

  return normalized.toUpperCase();
}

function inferCurrencyFromValue(value: string) {
  const normalized = normalizeCompactText(value);
  const alphabeticSuffix = normalized.match(/(?:^|\s)([A-Za-zА-Яа-я]{3,})$/u);
  if (alphabeticSuffix) {
    return normalizeCurrencyLabel(alphabeticSuffix[1]);
  }

  const compactDigits = normalized.replace(/[^\d]/g, "");
  const detectedCode = Object.keys(NUMERIC_CURRENCY_LABELS).find((code) => {
    return compactDigits.length > code.length + 2 && compactDigits.endsWith(code);
  });
  if (detectedCode) {
    return NUMERIC_CURRENCY_LABELS[detectedCode];
  }

  return null;
}

function stripTrailingCurrencyToken(value: string, currency?: string | null) {
  const normalized = normalizeCompactText(value);
  const normalizedCurrency = normalizeCurrencyLabel(currency);

  if (normalizedCurrency) {
    const knownNumericCode = Object.entries(NUMERIC_CURRENCY_LABELS).find(
      ([, label]) => label === normalizedCurrency,
    )?.[0];

    if (knownNumericCode) {
      const suffixPattern = new RegExp(`(?:\\s|\\u00A0)${knownNumericCode}$`);
      if (suffixPattern.test(normalized)) {
        return normalized.replace(suffixPattern, "").trim();
      }
      if (normalized.replace(/[^\d]/g, "").endsWith(knownNumericCode)) {
        return normalized.replace(new RegExp(`${knownNumericCode}$`), "").trim();
      }
    }

    const currencyPattern = new RegExp(`(?:\\s|\\u00A0)${normalizedCurrency}$`, "i");
    if (currencyPattern.test(normalized)) {
      return normalized.replace(currencyPattern, "").trim();
    }
  }

  const compactDigits = normalized.replace(/[^\d]/g, "");
  const detectedCode = Object.keys(NUMERIC_CURRENCY_LABELS).find((code) => {
    return compactDigits.length > code.length + 2 && compactDigits.endsWith(code);
  });

  if (detectedCode) {
    const suffixPattern = new RegExp(`(?:\\s|\\u00A0)?${detectedCode}$`);
    return normalized.replace(suffixPattern, "").trim();
  }

  const trailingToken = normalized.match(/(?:^|\s)([A-Za-zА-Яа-я]{3,})$/u);
  if (trailingToken) {
    const token = trailingToken[1];
    if (Object.values(NUMERIC_CURRENCY_LABELS).includes(token.toUpperCase())) {
      return normalized.slice(0, trailingToken.index ?? normalized.length).trim();
    }
    return normalized.replace(new RegExp(`(?:\\s|\\u00A0)${token}$`, "u"), "").trim();
  }

  return normalized;
}

export function parseMoneyValue(value: string | number | null | undefined, currency?: string | null) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }

  if (value == null) {
    return 0;
  }

  const stripped = stripTrailingCurrencyToken(String(value), currency);
  const normalized = stripped.replace(/\s+/g, "").replace(",", ".");
  const numeric = Number.parseFloat(normalized.replace(/[^0-9.-]/g, ""));
  return Number.isFinite(numeric) ? numeric : 0;
}

export function formatMoneyValue(
  value: string | number | null | undefined,
  currency?: string | null,
): string {
  const normalizedCurrency = normalizeCurrencyLabel(currency) ?? (typeof value === "string" ? inferCurrencyFromValue(value) : null);

  if (value == null) {
    return normalizedCurrency ? `0 ${normalizedCurrency}` : "0";
  }

  const raw = typeof value === "number" ? String(value) : normalizeCompactText(value);
  const parsed = parseMoneyValue(raw, currency);
  const hasMeaningfulSuffix = /[A-Za-zА-Яа-я]{3,}$/.test(raw) || /\d{3}$/.test(raw);

  if (!Number.isFinite(parsed)) {
    if (normalizedCurrency && !hasMeaningfulSuffix) {
      return `${raw} ${normalizedCurrency}`.trim();
    }
    return raw;
  }

  const formatted = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(parsed);

  if (normalizedCurrency) {
    return `${formatted} ${normalizedCurrency}`;
  }

  if (hasMeaningfulSuffix && /[A-Za-zА-Яа-я]{3,}$/.test(raw)) {
    return raw;
  }

  return formatted;
}
