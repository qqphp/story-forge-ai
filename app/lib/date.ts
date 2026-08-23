const SHANGHAI_OFFSET_SECONDS = 8 * 60 * 60;

function shanghaiParts(epochSeconds: number) {
  const date = new Date((epochSeconds + SHANGHAI_OFFSET_SECONDS) * 1000);
  return {
    year: date.getUTCFullYear(),
    month: date.getUTCMonth() + 1,
    day: date.getUTCDate(),
    hours: String(date.getUTCHours()).padStart(2, "0"),
    minutes: String(date.getUTCMinutes()).padStart(2, "0"),
    seconds: String(date.getUTCSeconds()).padStart(2, "0"),
  };
}

export function formatShanghaiShortDate(epochSeconds: number) {
  const value = shanghaiParts(epochSeconds);
  return `${value.month}月${value.day}日`;
}

export function formatShanghaiDateTime(epochSeconds: number) {
  const value = shanghaiParts(epochSeconds);
  return `${value.year}/${value.month}/${value.day} ${value.hours}:${value.minutes}:${value.seconds}`;
}
