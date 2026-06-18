import { GithubIcon } from "@/components/icons/GithubIcon"
import { GITHUB_REPO_URL } from "@/lib/siteLinks"
import { cn } from "@/lib/utils"

interface GithubRepoLinkProps {
  className?: string
  label?: string
  showLabel?: boolean
}

export function GithubRepoLink({
  className,
  label = "GitHub 项目 README",
  showLabel = true,
}: GithubRepoLinkProps) {
  return (
    <a
      href={GITHUB_REPO_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "inline-flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground",
        className,
      )}
    >
      <GithubIcon />
      {showLabel && <span>{label}</span>}
    </a>
  )
}
