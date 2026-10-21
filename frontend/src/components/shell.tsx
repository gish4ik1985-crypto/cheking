import { useEffect, useState } from "react"
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom"
import { ADMIN_TABS, adminTabNow } from "@/lib/adminTabs"
import { useTheme } from "@/lib/theme"
import { useAuth } from "@/lib/auth"
import { api } from "@/lib/api"
import { jobWhen } from "@/lib/format"
import type { HistoryItem } from "@/lib/types"
import { FileCheck2, History, KeyRound, LogOut, Moon, Settings2, Sun, Upload, UserRound, ChevronDown, TriangleAlert } from "lucide-react"
import {
  Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupContent, SidebarGroupLabel, SidebarHeader, SidebarInset,
  SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarMenuSub, SidebarMenuSubButton, SidebarMenuSubItem, SidebarProvider, SidebarTrigger,
} from "@/components/ui/sidebar"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Separator } from "@/components/ui/separator"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  return (
    <Button variant="ghost" size="icon" aria-label="Сменить тему" onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
      <Sun className="size-4 dark:hidden" /><Moon className="hidden size-4 dark:block" />
    </Button>
  )
}

export const PAGE_TITLES: Record<string, string> = { "/": "Новая проверка", "/admin": "Настройки проверки", "/profile": "Профиль" }

export default function Shell() {
  const { me, isAdmin, logout } = useAuth()
  const loc = useLocation()
  const nav = useNavigate()
  const [open, setOpen] = useState(true)
  const [sp] = useSearchParams()
  const [setOpenTree, setSetOpenTree] = useState(true)
  const [hist, setHist] = useState<HistoryItem[]>([])
  const onJob = loc.pathname.startsWith("/job/")

  // на странице отчёта боковое меню сворачивается — чтобы лист и замечания получили всю ширину
  useEffect(() => { if (onJob) setOpen(false) }, [onJob])
  useEffect(() => { api<HistoryItem[]>("/api/history").then(h => setHist(h.slice(0, 6))).catch(() => {}) }, [loc.pathname])

  const title = onJob ? "Отчёт проверки" : PAGE_TITLES[loc.pathname] ?? ""
  const initials = (me?.name ?? "?").slice(0, 2).toUpperCase()

  return (
    <TooltipProvider>
      <SidebarProvider open={open} onOpenChange={setOpen}>
        <Sidebar collapsible="icon">
          <SidebarHeader>
            <Link to="/" className="flex items-center gap-2 px-1 py-1.5">
              <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground"><FileCheck2 className="size-4.5" /></div>
              <div className="grid leading-tight group-data-[collapsible=icon]:hidden">
                <span className="text-sm font-semibold">Проверка чертежей</span>
                <span className="text-xs text-muted-foreground">ЕСКД · локально</span>
              </div>
            </Link>
          </SidebarHeader>
          <SidebarContent>
            <SidebarGroup>
              <SidebarGroupLabel>Работа</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton isActive={loc.pathname === "/"} tooltip="Новая проверка" render={<NavLink to="/" />}><Upload /><span>Новая проверка</span></SidebarMenuButton>
                  </SidebarMenuItem>
                  {isAdmin && (
                    <SidebarMenuItem>
                      <SidebarMenuButton tooltip="Настройки" isActive={loc.pathname === "/admin"} onClick={() => setSetOpenTree(o => !o)}>
                        <Settings2 /><span>Настройки</span>
                        <ChevronDown className={"ml-auto size-4 transition-transform " + (setOpenTree ? "" : "-rotate-90")} />
                      </SidebarMenuButton>
                      {setOpenTree && (
                        <SidebarMenuSub>
                          {ADMIN_TABS.map(([k, t]) => (
                            <SidebarMenuSubItem key={k}>
                              <SidebarMenuSubButton
                                isActive={loc.pathname === "/admin" && adminTabNow(sp) === k}
                                render={<NavLink to={"/admin?tab=" + k} onClick={() => { try { localStorage.setItem("admin-tab", k) } catch { /* без хранилища */ } }} />}
                              ><span>{t}</span></SidebarMenuSubButton>
                            </SidebarMenuSubItem>
                          ))}
                        </SidebarMenuSub>
                      )}
                    </SidebarMenuItem>
                  )}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
            {hist.length > 0 && (
              <SidebarGroup className="group-data-[collapsible=icon]:hidden">
                <SidebarGroupLabel><History className="mr-1.5 size-3.5" />Последние проверки</SidebarGroupLabel>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {hist.map(h => (
                      <SidebarMenuItem key={h.id}>
                        <SidebarMenuButton isActive={loc.pathname === "/job/" + h.id} size="sm" className="h-auto py-1.5" render={<NavLink to={"/job/" + h.id} />}>
                          <span className="grid leading-tight">
                            <span className="text-xs">{jobWhen(h.id)} · {h.count} док.</span>
                            <span className="text-[11px] text-muted-foreground">
                              <span className="text-[var(--sev-error)]">{h.errors} ош.</span> · <span className="text-[var(--sev-warn)]">{h.warnings} пр.</span>
                            </span>
                          </span>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            )}
          </SidebarContent>
          <SidebarFooter>
            <DropdownMenu>
              <DropdownMenuTrigger render={<SidebarMenuButton size="lg" />}>
                <Avatar className="size-8 rounded-lg"><AvatarFallback className="rounded-lg">{initials}</AvatarFallback></Avatar>
                <div className="grid text-left leading-tight">
                  <span className="text-sm font-medium">{me?.name}</span>
                  <span className="text-xs text-muted-foreground">{isAdmin ? "администратор" : "пользователь"}</span>
                </div>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" align="start" className="w-60">
                <DropdownMenuLabel>{me?.name}{me?.version ? ` · версия ${me.version}` : ""}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => nav("/profile")}><UserRound />Профиль</DropdownMenuItem>
                <DropdownMenuItem onClick={() => nav("/profile")}><KeyRound />Сменить пароль</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => void logout()}><LogOut />Выйти</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarFooter>
        </Sidebar>
        <SidebarInset className="min-w-0">
          <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur">
            <SidebarTrigger />
            <Separator orientation="vertical" className="mx-1 h-5" />
            <div className="min-w-0 flex-1 truncate text-sm font-medium" id="page-title">{title}</div>
            <div id="header-actions" className="flex items-center gap-2" />
            <ThemeToggle />
          </header>
          {me?.default_password && (
            <div className="flex items-center gap-2 border-b bg-[var(--sev-warn-bg)] px-4 py-2 text-sm text-[var(--sev-warn)]">
              <TriangleAlert className="size-4" />
              У вас пароль по умолчанию. <Link to="/profile" className="font-medium underline">Смените пароль в профиле</Link>.
            </div>
          )}
          <main className="min-h-0 flex-1"><Outlet /></main>
        </SidebarInset>
        <Toaster richColors position="bottom-right" />
      </SidebarProvider>
    </TooltipProvider>
  )
}
