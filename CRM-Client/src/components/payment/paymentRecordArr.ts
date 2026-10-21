export interface ArrPoint {
  ratio: number | null
}

/** Defined months in order. Empty months are left out so the line spans them instead of breaking. */
export function arrLinePoints<T extends ArrPoint>(points: T[]): T[] {
  return points.filter((point) => point.ratio !== null)
}

/** A lone month has no segment length, so the chart draws a dot. */
export function arrShowsMarker<T extends ArrPoint>(points: T[]): boolean {
  return arrLinePoints(points).length === 1
}

export function arrCanOpen(ratio: number | null): boolean {
  return ratio !== null
}
