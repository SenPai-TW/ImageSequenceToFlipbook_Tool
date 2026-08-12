const NUMBER_PART = /(\d+)/g;

export function naturalCompare(left: string, right: string): number {
  const leftParts = left.toLocaleLowerCase().split(NUMBER_PART);
  const rightParts = right.toLocaleLowerCase().split(NUMBER_PART);
  const length = Math.max(leftParts.length, rightParts.length);

  for (let index = 0; index < length; index += 1) {
    const leftPart = leftParts[index] ?? "";
    const rightPart = rightParts[index] ?? "";
    const leftNumber = /^\d+$/.test(leftPart) ? Number(leftPart) : null;
    const rightNumber = /^\d+$/.test(rightPart) ? Number(rightPart) : null;

    if (leftNumber !== null && rightNumber !== null && leftNumber !== rightNumber) {
      return leftNumber - rightNumber;
    }
    const compared = leftPart.localeCompare(rightPart, undefined, { sensitivity: "base" });
    if (compared !== 0) return compared;
  }
  return left.localeCompare(right, undefined, { sensitivity: "base" });
}

export function naturalSortFiles(files: readonly File[]): File[] {
  return [...files].sort((left, right) => naturalCompare(left.name, right.name));
}

export function evenIndices(frameCount: number, wanted: number): number[] {
  const available = Math.max(0, Math.floor(frameCount));
  const count = Math.min(available, Math.max(0, Math.floor(wanted)));
  if (count === 0) return [];
  if (count === 1) return [0];
  if (count >= available) return Array.from({ length: available }, (_, index) => index);

  return Array.from(
    { length: count },
    (_, index) => Math.floor((index * (available - 1)) / (count - 1)),
  );
}

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLocaleLowerCase() : "";
}

export const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".tif", ".tiff"]);
export const VIDEO_EXTENSIONS = new Set([".mp4", ".mov"]);

export function supportedImageFiles(files: readonly File[]): File[] {
  return naturalSortFiles(files.filter((file) => IMAGE_EXTENSIONS.has(extensionOf(file.name))));
}
