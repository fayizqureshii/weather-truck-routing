import { scoreToRgba } from './risk'
import type { Heatmap, HeatmapGrid } from './types'

export interface HeatmapFrames {
  /** One PNG data URL per forecast hour, each `cols x rows` pixels (one pixel per cell). */
  urls: string[]
  /** Image corners for a MapLibre image source: TL, TR, BR, BL as [lon, lat]. */
  coordinates: [[number, number], [number, number], [number, number], [number, number]]
  /** cellIndex[row * cols + col] -> index into heatmap arrays, or -1 outside the corridor. */
  cellIndex: Int32Array
}

/**
 * Pre-render every hour of the forecast to a tiny image up front, so moving the slider is
 * just an image swap on the GPU (no re-computation, no network).
 * The grid is regular in Web Mercator, so pixels line up exactly with the map.
 */
export function buildFrames(grid: HeatmapGrid, heatmap: Heatmap): HeatmapFrames {
  const { cols, rows } = grid
  const canvas = document.createElement('canvas')
  canvas.width = cols
  canvas.height = rows
  const ctx = canvas.getContext('2d')!
  const cellIndex = new Int32Array(cols * rows).fill(-1)
  grid.cells.forEach(([row, col], i) => {
    cellIndex[row * cols + col] = i
  })

  const urls = heatmap.scores.map((scores) => {
    const image = ctx.createImageData(cols, rows)
    grid.cells.forEach(([row, col], i) => {
      const [r, g, b, a] = scoreToRgba(scores[i])
      const p = (row * cols + col) * 4
      image.data[p] = r
      image.data[p + 1] = g
      image.data[p + 2] = b
      image.data[p + 3] = a
    })
    ctx.putImageData(image, 0, 0)
    return canvas.toDataURL('image/png')
  })

  return {
    urls,
    coordinates: [
      [grid.west, grid.north],
      [grid.east, grid.north],
      [grid.east, grid.south],
      [grid.west, grid.south],
    ],
    cellIndex,
  }
}

function mercY(lat: number): number {
  return (Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) * 180) / Math.PI
}

/** Which heatmap cell (index into the heatmap arrays) contains a map position, if any. */
export function cellAt(grid: HeatmapGrid, frames: HeatmapFrames, lon: number, lat: number): number {
  const col = Math.floor(((lon - grid.west) / (grid.east - grid.west)) * grid.cols)
  const yTop = mercY(grid.north)
  const yBottom = mercY(grid.south)
  const row = Math.floor(((yTop - mercY(lat)) / (yTop - yBottom)) * grid.rows)
  if (col < 0 || row < 0 || col >= grid.cols || row >= grid.rows) return -1
  return frames.cellIndex[row * grid.cols + col]
}
