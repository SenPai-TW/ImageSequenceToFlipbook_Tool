import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconBase({ children, ...props }: IconProps): React.ReactElement {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      {children}
    </svg>
  );
}

export function GridIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></IconBase>;
}

export function ImagesIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><rect x="3" y="5" width="16" height="14" rx="2" /><path d="m6 16 4-4 3 3 2-2 4 4" /><path d="M7.5 9h.01" /><path d="M7 2h12a2 2 0 0 1 2 2v12" /></IconBase>;
}

export function VideoIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><rect x="3" y="5" width="14" height="14" rx="2" /><path d="m17 10 4-2v8l-4-2" /></IconBase>;
}

export function UploadIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M5 14v5h14v-5" /></IconBase>;
}

export function FolderIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /></IconBase>;
}

export function ShieldIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><path d="M12 3 5 6v5c0 4.4 2.7 8 7 10 4.3-2 7-5.6 7-10V6Z" /><path d="m9 12 2 2 4-4" /></IconBase>;
}

export function DownloadIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></IconBase>;
}

export function MoonIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" /></IconBase>;
}

export function SunIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41" /></IconBase>;
}

export function AlertIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><path d="M10.3 4.2 2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></IconBase>;
}

export function CloseIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><path d="m6 6 12 12M18 6 6 18" /></IconBase>;
}

export function CheckIcon(props: IconProps): React.ReactElement {
  return <IconBase {...props}><path d="m5 12 4 4L19 6" /></IconBase>;
}
