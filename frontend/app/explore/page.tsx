"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Compass,
  Search,
  BookOpen,
  Clock,
  Star,
  CheckCircle2,
  ArrowRight,
  Filter,
  GraduationCap,
  Layers,
} from "lucide-react";

import { AppShell, PageHeader } from "@/components/shell";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Badge,
  Button,
  Input,
  Progress,
  Skeleton,
  EmptyState,
  ErrorState,
  useToast,
} from "@/components/ui";
import { apiClient } from "@/lib/api-client";
import { useApi } from "@/hooks/use-api";
import { formatMinutes } from "@/lib/utils";

interface ContentItem {
  id: string;
  title: string;
  content_type: string;
  duration_seconds: number;
  status: string;
}

interface Module {
  id: string;
  title: string;
  description: string;
  sequence_order: number;
  estimated_duration_mins: number;
  content_items: ContentItem[];
}

interface Course {
  id: string;
  title: string;
  code: string;
  description: string;
  category: string;
  difficulty: "beginner" | "intermediate" | "advanced";
  /** null until real ratings exist — never shown as a placeholder. */
  rating: number | null;
  /** null when the course has no timed content. */
  duration_minutes: number | null;
  enrollment_count?: number;
  /** Names of the competencies the course develops. */
  skills?: string[];
  thumbnail_url: string | null;
  instructor_name: string | null;
  is_enrolled: boolean;
  progress_pct: number;
  modules: Module[];
}

const CATEGORIES = [
  "All",
  "Computer Science",
  "Data Science",
  "Engineering",
  "Artificial Intelligence",
];

const DIFFICULTIES = [
  { label: "All Levels", value: "all" },
  { label: "Beginner", value: "beginner" },
  { label: "Intermediate", value: "intermediate" },
  { label: "Advanced", value: "advanced" },
];

export default function ExplorePage() {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [selectedDifficulty, setSelectedDifficulty] = useState("all");
  const [sortBy, setSortBy] = useState("popular");
  const [enrollingId, setEnrollingId] = useState<string | null>(null);

  const { data: courses, loading, error, refetch, setData } = useApi<Course[]>(
    (signal) => {
      const params: Record<string, string> = {
        sort_by: sortBy,
      };
      if (selectedCategory !== "All") params.category = selectedCategory;
      if (selectedDifficulty !== "all") params.difficulty = selectedDifficulty;
      if (searchQuery.trim()) params.search = searchQuery.trim();

      return apiClient.get<Course[]>("/api/v1/courses", { params, signal });
    },
    { deps: [selectedCategory, selectedDifficulty, sortBy, searchQuery] }
  );

  const handleEnroll = async (course: Course) => {
    try {
      setEnrollingId(course.id);
      await apiClient.post(`/api/v1/courses/${course.id}/enroll`);

      // Optimistically update local state
      if (courses) {
        setData(
          courses.map((c) =>
            c.id === course.id
              ? { ...c, is_enrolled: true, progress_pct: c.progress_pct || 0 }
              : c
          )
        );
      }

      toast({
        title: "Successfully Enrolled!",
        description: `You are now enrolled in ${course.title}. Start learning today!`,
        variant: "success",
      });
    } catch (err) {
      toast({
        title: "Enrollment Failed",
        description: err instanceof Error ? err.message : "Could not complete enrollment.",
        variant: "error",
      });
    } finally {
      setEnrollingId(null);
    }
  };

  const difficultyVariant = (difficulty: string) => {
    switch (difficulty.toLowerCase()) {
      case "beginner":
        return "info" as const;
      case "intermediate":
        return "primary" as const;
      case "advanced":
        return "danger" as const;
      default:
        return "neutral" as const;
    }
  };

  return (
    <AppShell>
      <PageHeader
        title="Explore Courses"
        description="Master verified engineering competencies, adaptive curriculums, and enterprise skills."
        actions={
          <Link href="/learner/my-learning">
            <Button variant="outline" size="sm">
              <BookOpen className="h-4 w-4" />
              My Learning
            </Button>
          </Link>
        }
      />

      {/* Filter and Search Bar */}
      <div className="mb-8 space-y-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-muted" />
            <Input
              type="search"
              placeholder="Search courses, skills, or curriculum codes..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 bg-surface-elevated"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-fg-muted" />
              <select
                aria-label="Filter courses by difficulty level"
                value={selectedDifficulty}
                onChange={(e) => setSelectedDifficulty(e.target.value)}
                className="h-9 rounded-md border border-border bg-surface-elevated px-3 text-xs font-medium text-fg focus:outline-none focus:ring-1 focus:ring-accent"
              >
                {DIFFICULTIES.map((diff) => (
                  <option key={diff.value} value={diff.value}>
                    {diff.label}
                  </option>
                ))}
              </select>
            </div>

            <select
              aria-label="Sort courses order"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="h-9 rounded-md border border-border bg-surface-elevated px-3 text-xs font-medium text-fg focus:outline-none focus:ring-1 focus:ring-accent"
            >
              <option value="popular">Most Enrolled</option>
              <option value="newest">Recently Added</option>
              <option value="title">Alphabetical (A-Z)</option>
            </select>
          </div>
        </div>

        {/* Category Pills */}
        <div className="flex flex-wrap gap-2 pt-1">
          {CATEGORIES.map((category) => {
            const isSelected = selectedCategory === category;
            return (
              <button
                key={category}
                onClick={() => setSelectedCategory(category)}
                className={`inline-flex items-center rounded-full px-3.5 py-1.5 text-xs font-medium transition-all ${
                  isSelected
                    ? "bg-accent text-accent-contrast shadow-sm"
                    : "bg-surface-elevated text-fg-muted hover:bg-surface-subtle hover:text-fg border border-border"
                }`}
              >
                {category}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Course Grid */}
      {loading ? (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="overflow-hidden bg-surface-elevated">
              <Skeleton className="h-44 w-full" />
              <CardHeader className="space-y-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-6 w-3/4" />
                <Skeleton className="h-4 w-full" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : error ? (
        <ErrorState
          title="Could not load courses"
          error={error}
          onRetry={refetch}
        />
      ) : !courses || courses.length === 0 ? (
        <EmptyState
          icon={Compass}
          title="No courses found"
          description={
            searchQuery || selectedCategory !== "All" || selectedDifficulty !== "all"
              ? "Try adjusting your search criteria or category filter."
              : "No courses are currently published in your organization."
          }
          action={
            (searchQuery || selectedCategory !== "All" || selectedDifficulty !== "all") ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSearchQuery("");
                  setSelectedCategory("All");
                  setSelectedDifficulty("all");
                }}
              >
                Reset Filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {courses.map((course) => {
            const totalModules = course.modules?.length || 0;
            const totalItems =
              course.modules?.reduce(
                (acc, m) => acc + (m.content_items?.length || 0),
                0
              ) || 0;

            return (
              <Card
                key={course.id}
                className="group flex flex-col justify-between overflow-hidden border border-border bg-surface-elevated transition-all duration-200 hover:-translate-y-1 hover:border-accent/40 hover:shadow-lg"
              >
                <div>
                  {/* Thumbnail / Header Banner */}
                  <div className="relative h-44 w-full overflow-hidden bg-surface-subtle">
                    {course.thumbnail_url ? (
                      /* eslint-disable-next-line @next/next/no-img-element */
                      <img
                        src={course.thumbnail_url}
                        alt={course.title}
                        className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                      />
                    ) : (
                      <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-accent/10 to-surface-subtle text-accent">
                        <GraduationCap className="h-16 w-16 opacity-40" />
                      </div>
                    )}

                    <div className="absolute left-3 top-3 flex gap-2">
                      <Badge variant="neutral" className="backdrop-blur-md bg-surface/80">
                        {course.category}
                      </Badge>
                      <Badge variant={difficultyVariant(course.difficulty)} className="backdrop-blur-md">
                        {course.difficulty}
                      </Badge>
                    </div>

                    {course.is_enrolled && (
                      <div className="absolute right-3 top-3">
                        <Badge variant="primary" className="flex items-center gap-1 shadow-sm">
                          <CheckCircle2 className="h-3 w-3" />
                          Enrolled
                        </Badge>
                      </div>
                    )}
                  </div>

                  <CardHeader className="space-y-1.5 pb-2">
                    <div className="flex items-center justify-between text-xs text-fg-muted">
                      <span className="font-mono font-medium">{course.code}</span>
                      {course.rating !== null && (
                        <div className="flex items-center gap-1 text-amber-500 font-semibold">
                          <Star className="h-3.5 w-3.5 fill-amber-500 text-amber-500" />
                          <span>{course.rating.toFixed(1)}</span>
                        </div>
                      )}
                    </div>

                    <CardTitle className="line-clamp-1 text-lg font-semibold text-fg group-hover:text-accent transition-colors">
                      <Link href={`/courses/${course.id}`}>{course.title}</Link>
                    </CardTitle>

                    <CardDescription className="line-clamp-2 text-xs leading-relaxed text-fg-muted">
                      {course.description}
                    </CardDescription>
                  </CardHeader>

                  <CardContent className="space-y-3 pb-4 text-xs text-fg-muted">
                    {course.skills && course.skills.length > 0 && (
                      <ul className="flex flex-wrap gap-1.5" aria-label="Skills you will build">
                        {course.skills.slice(0, 3).map((skill) => (
                          <li key={skill}>
                            <Badge variant="neutral" className="max-w-[12rem] truncate">{skill}</Badge>
                          </li>
                        ))}
                        {course.skills.length > 3 && (
                          <li className="text-[11px] text-fg-muted self-center">+{course.skills.length - 3} more</li>
                        )}
                      </ul>
                    )}

                    <div className="flex items-center justify-between border-t border-border pt-3">
                      {course.duration_minutes !== null && (
                        <div className="flex items-center gap-1.5">
                          <Clock className="h-3.5 w-3.5" />
                          <span>{formatMinutes(course.duration_minutes)}</span>
                        </div>
                      )}
                      <div className="flex items-center gap-1.5">
                        <Layers className="h-3.5 w-3.5" />
                        <span>
                          {totalModules} {totalModules === 1 ? "module" : "modules"} • {totalItems} items
                        </span>
                      </div>
                    </div>

                    {course.is_enrolled && (
                      <div className="space-y-1.5 pt-1">
                        <div className="flex justify-between text-[11px] font-medium">
                          <span className="text-fg-muted">Course Progress</span>
                          <span className="text-accent">{Math.round(course.progress_pct || 0)}%</span>
                        </div>
                        <Progress value={course.progress_pct || 0} size="sm" tone="primary" />
                      </div>
                    )}
                  </CardContent>
                </div>

                <CardFooter className="border-t border-border bg-surface-subtle/40 pt-3 pb-3 flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] text-fg-muted font-medium">
                    {course.instructor_name ?? ""}
                  </span>

                  <div className="flex items-center gap-2">
                    <Link href={`/courses/${course.id}`}>
                      <Button variant="ghost" size="sm" className="h-8 px-2.5 text-xs">
                        Details
                      </Button>
                    </Link>

                    {course.is_enrolled ? (
                      <Link href={`/learner/learning?course_id=${course.id}`}>
                        <Button variant="primary" size="sm" className="h-8 gap-1 px-3 text-xs">
                          Continue
                          <ArrowRight className="h-3 w-3" />
                        </Button>
                      </Link>
                    ) : (
                      <Button
                        variant="primary"
                        size="sm"
                        className="h-8 gap-1 px-3 text-xs"
                        loading={enrollingId === course.id}
                        onClick={() => handleEnroll(course)}
                      >
                        Enroll Now
                      </Button>
                    )}
                  </div>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
